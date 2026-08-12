"""Deterministic commercial path, availability, slot, and pricing policies."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.domain.commercial import (
    Booking,
    BookingRequest,
    BookingStatus,
    CommercialPath,
    MONEY_QUANTUM,
    QuoteLine,
    TimeSlot,
    require_money,
)


UTC = timezone.utc
ACTIVE_BOOKING_STATUSES = frozenset({
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.RESCHEDULED,
})


def find_service(business_dna: Mapping[str, Any], service_id: str) -> Mapping[str, Any]:
    for service in business_dna.get("services", []):
        if isinstance(service, Mapping) and service.get("id") == service_id:
            return service
    raise ValueError(f"Business DNA has no service: {service_id}")


class CommercialPathSelector:
    """Business DNA is the sole authority for the post-qualification path."""

    _PATHS = {
        "bookable": CommercialPath.BOOKING,
        "quote_required": CommercialPath.QUOTE,
        "direct_sale": CommercialPath.DIRECT_NEXT_STEP,
        "human_review": CommercialPath.HUMAN_REVIEW,
    }

    def select(self, business_dna: Mapping[str, Any], service_id: str) -> CommercialPath:
        service = find_service(business_dna, service_id)
        configured = service.get("fulfillment_type")
        if not isinstance(configured, str) or configured not in self._PATHS:
            raise ValueError("service fulfillment_type is missing or unsupported")
        path = self._PATHS[configured]
        if path is CommercialPath.BOOKING:
            booking = business_dna.get("booking", {})
            if not service.get("booking_allowed", False) or not (
                isinstance(booking, Mapping) and booking.get("enabled", False)
            ):
                return CommercialPath.HUMAN_REVIEW
        return path


class AvailabilityProvider(Protocol):
    def available_slots(
        self,
        request: BookingRequest,
        business_dna: Mapping[str, Any],
        existing_bookings: Iterable[Booking],
        *,
        now: datetime,
    ) -> tuple[TimeSlot, ...]: ...


class DeterministicAvailabilityEngine:
    """Calculates bounded slots only from Business DNA and persisted bookings."""

    def available_slots(
        self,
        request: BookingRequest,
        business_dna: Mapping[str, Any],
        existing_bookings: Iterable[Booking],
        *,
        now: datetime,
    ) -> tuple[TimeSlot, ...]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("availability now must be timezone-aware")
        service = find_service(business_dna, request.service_id)
        booking = business_dna.get("booking", {})
        if not isinstance(booking, Mapping) or not booking.get("enabled", False):
            return ()
        timezone_name = str(booking.get("timezone") or business_dna["business"]["timezone"])
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("booking timezone is not available") from exc
        duration = int(booking.get("appointment_duration_minutes") or service["duration_minutes"])
        interval = int(booking.get("slot_interval_minutes", 30))
        buffer_before = int(booking.get("buffer_before_minutes", 0))
        buffer_after = int(booking.get("buffer_after_minutes", 0))
        capacity = int(booking.get("capacity", 1))
        allowed_days = {
            str(item).casefold() for item in booking.get("allowed_days", [])
        }
        business_hours = business_dna.get("business_hours", {})
        if not isinstance(business_hours, Mapping):
            raise ValueError("business_hours must be configured")
        configured_times = booking.get("allowed_times", [])
        persisted = tuple(
            item for item in existing_bookings if item.status in ACTIVE_BOOKING_STATUSES
        )
        earliest = max(request.earliest_start, now.astimezone(UTC)).astimezone(zone)
        latest = request.latest_start.astimezone(zone)
        slots: list[TimeSlot] = []
        current_day = earliest.date()
        while current_day <= latest.date() and len(slots) < request.maximum_slots:
            day_name = current_day.strftime("%A").casefold()
            if allowed_days and day_name not in allowed_days:
                current_day += timedelta(days=1)
                continue
            day_windows = business_hours.get(day_name, [])
            if not isinstance(day_windows, list):
                raise ValueError("business hours day entries must be arrays")
            windows = self._intersect_windows(day_windows, configured_times)
            for opens, closes in windows:
                local_open = datetime.combine(current_day, opens, tzinfo=zone)
                local_close = datetime.combine(current_day, closes, tzinfo=zone)
                cursor = self._ceil_local(max(local_open, earliest), interval)
                while cursor + timedelta(minutes=duration) <= local_close:
                    if cursor > latest:
                        break
                    local_end = cursor + timedelta(minutes=duration)
                    if not self._valid_local_time(cursor, zone) or not self._valid_local_time(
                        local_end, zone
                    ):
                        cursor += timedelta(minutes=interval)
                        continue
                    start_at = cursor.astimezone(UTC)
                    end_at = local_end.astimezone(UTC)
                    if end_at - start_at != timedelta(minutes=duration):
                        cursor += timedelta(minutes=interval)
                        continue
                    occupied = sum(
                        self._overlaps_with_buffers(
                            start_at,
                            end_at,
                            existing.start_at,
                            existing.end_at,
                            buffer_before,
                            buffer_after,
                        )
                        for existing in persisted
                    )
                    if occupied < capacity:
                        digest = hashlib.sha256(
                            "\x1f".join((
                                request.business_id,
                                request.service_id,
                                start_at.isoformat(),
                                end_at.isoformat(),
                            )).encode("utf-8")
                        ).hexdigest()[:32]
                        slots.append(TimeSlot(digest, start_at, end_at, timezone_name, capacity))
                        if len(slots) >= request.maximum_slots:
                            break
                    cursor += timedelta(minutes=interval)
            current_day += timedelta(days=1)
        return tuple(slots)

    @staticmethod
    def _parse_time(value: object) -> time:
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("booking times must use HH:MM")
        return time.fromisoformat(value)

    @classmethod
    def _intersect_windows(
        cls,
        business_windows: list[object],
        configured_times: object,
    ) -> tuple[tuple[time, time], ...]:
        base: list[tuple[time, time]] = []
        for window in business_windows:
            if not isinstance(window, Mapping):
                raise ValueError("business hours windows must be objects")
            opens = cls._parse_time(window.get("opens"))
            closes = cls._parse_time(window.get("closes"))
            if closes <= opens:
                raise ValueError("business hours must close after opening")
            base.append((opens, closes))
        if not configured_times:
            return tuple(base)
        if not isinstance(configured_times, list):
            raise ValueError("allowed_times must be an array")
        allowed: list[tuple[time, time]] = []
        for window in configured_times:
            if not isinstance(window, Mapping):
                raise ValueError("allowed time windows must be objects")
            opens = cls._parse_time(window.get("starts"))
            closes = cls._parse_time(window.get("ends"))
            if closes <= opens:
                raise ValueError("allowed time windows must end after they start")
            allowed.append((opens, closes))
        return tuple(
            (max(base_start, allowed_start), min(base_end, allowed_end))
            for base_start, base_end in base
            for allowed_start, allowed_end in allowed
            if max(base_start, allowed_start) < min(base_end, allowed_end)
        )

    @staticmethod
    def _ceil_local(value: datetime, interval_minutes: int) -> datetime:
        if interval_minutes < 1 or interval_minutes > 1_440:
            raise ValueError("slot interval must be between 1 and 1440 minutes")
        minute_of_day = value.hour * 60 + value.minute
        rounded = ((minute_of_day + interval_minutes - 1) // interval_minutes) * interval_minutes
        day_offset, minute = divmod(rounded, 1_440)
        return value.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=day_offset, minutes=minute
        )

    @staticmethod
    def _valid_local_time(value: datetime, zone: ZoneInfo) -> bool:
        round_trip = value.astimezone(UTC).astimezone(zone)
        return round_trip.replace(fold=value.fold) == value

    @staticmethod
    def _overlaps_with_buffers(
        candidate_start: datetime,
        candidate_end: datetime,
        existing_start: datetime,
        existing_end: datetime,
        buffer_before: int,
        buffer_after: int,
    ) -> bool:
        candidate_block_start = candidate_start - timedelta(minutes=buffer_before)
        candidate_block_end = candidate_end + timedelta(minutes=buffer_after)
        existing_block_start = existing_start - timedelta(minutes=buffer_before)
        existing_block_end = existing_end + timedelta(minutes=buffer_after)
        return candidate_block_start < existing_block_end and existing_block_start < candidate_block_end


@dataclass(frozen=True, slots=True)
class SlotPreference:
    selected: TimeSlot | None
    candidates: tuple[TimeSlot, ...] = ()


class SlotPreferenceInterpreter(Protocol):
    def interpret(
        self,
        customer_text: str,
        proposed_slots: tuple[TimeSlot, ...],
        *,
        now: datetime,
    ) -> SlotPreference: ...


class DeterministicSlotPreferenceInterpreter:
    """Resolves preferences only against the server-proposed slot set."""

    _ORDINALS = {
        "first": 0,
        "1st": 0,
        "second": 1,
        "2nd": 1,
        "third": 2,
        "3rd": 2,
        "fourth": 3,
        "4th": 3,
        "fifth": 4,
        "5th": 4,
    }

    def interpret(
        self,
        customer_text: str,
        proposed_slots: tuple[TimeSlot, ...],
        *,
        now: datetime,
    ) -> SlotPreference:
        text_value = customer_text.strip().casefold()
        for word, index in self._ORDINALS.items():
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text_value):
                return SlotPreference(
                    proposed_slots[index] if index < len(proposed_slots) else None
                )
        numeric = re.fullmatch(r"(?:option\s*)?([1-9])", text_value)
        if numeric:
            index = int(numeric.group(1)) - 1
            return SlotPreference(proposed_slots[index] if index < len(proposed_slots) else None)

        matches = list(proposed_slots)
        if "tomorrow" in text_value:
            target_dates = {
                (now.astimezone(ZoneInfo(slot.timezone)).date() + timedelta(days=1), slot.timezone)
                for slot in proposed_slots
            }
            matches = [
                slot
                for slot in matches
                if (slot.start_at.astimezone(ZoneInfo(slot.timezone)).date(), slot.timezone)
                in target_dates
            ]
        weekdays = {
            name
            for name in (
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
            )
            if name in text_value
        }
        if weekdays:
            matches = [
                slot
                for slot in matches
                if slot.start_at.astimezone(ZoneInfo(slot.timezone)).strftime("%A").casefold()
                in weekdays
            ]
        if "morning" in text_value:
            matches = [slot for slot in matches if slot.start_at.astimezone(ZoneInfo(slot.timezone)).hour < 12]
        elif "afternoon" in text_value:
            matches = [
                slot for slot in matches
                if 12 <= slot.start_at.astimezone(ZoneInfo(slot.timezone)).hour < 17
            ]
        elif "evening" in text_value:
            matches = [slot for slot in matches if slot.start_at.astimezone(ZoneInfo(slot.timezone)).hour >= 17]
        time_match = re.search(r"\b(?:at\s+)?(1[0-2]|[1-9])(?::([0-5]\d))?\s*(am|pm)?\b", text_value)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            suffix = time_match.group(3)
            candidate_hours = {hour % 12 + (12 if suffix == "pm" else 0)} if suffix else {
                hour,
                hour + 12 if hour <= 7 else hour,
            }
            matches = [
                slot
                for slot in matches
                if (
                    slot.start_at.astimezone(ZoneInfo(slot.timezone)).hour in candidate_hours
                    and slot.start_at.astimezone(ZoneInfo(slot.timezone)).minute == minute
                )
            ]
        if len(matches) == 1 and matches != list(proposed_slots):
            return SlotPreference(matches[0])
        if matches and matches != list(proposed_slots):
            return SlotPreference(None, tuple(matches))
        return SlotPreference(None)


@dataclass(frozen=True, slots=True)
class PricingDecision:
    line: QuoteLine | None
    subtotal: Decimal | None
    total: Decimal | None
    missing_inputs: tuple[str, ...]
    requires_human: bool
    pricing_basis: Mapping[str, Any]
    reason: str


class DeterministicPricingEngine:
    """Calculates customer prices from explicit Business DNA rules only."""

    def calculate(
        self,
        service: Mapping[str, Any],
        currency: str,
        pricing_inputs: Mapping[str, Decimal],
    ) -> PricingDecision:
        quoting = service.get("quoting", {})
        if not isinstance(quoting, Mapping):
            raise ValueError("service quoting configuration must be an object")
        required = tuple(str(item) for item in quoting.get("required_pricing_inputs", []))
        missing = tuple(item for item in required if item not in pricing_inputs)
        if missing:
            return PricingDecision(
                None, None, None, missing, False, {}, "Required pricing inputs are missing"
            )
        pricing_type = quoting.get("pricing_type")
        total: Decimal | None = None
        basis: dict[str, Any] = {"pricing_type": pricing_type, "inputs_used": sorted(required)}
        if pricing_type == "fixed":
            total = self._decimal(quoting.get("fixed_price"), "fixed_price")
        elif pricing_type == "formula":
            formula = quoting.get("formula", {})
            if not isinstance(formula, Mapping):
                raise ValueError("formula pricing requires a formula object")
            total = self._decimal(formula.get("base_amount", "0.00"), "base_amount")
            components = formula.get("components", [])
            if not isinstance(components, list):
                raise ValueError("formula components must be an array")
            for component in components:
                if not isinstance(component, Mapping):
                    raise ValueError("formula components must be objects")
                input_name = str(component.get("input"))
                if input_name not in pricing_inputs:
                    raise ValueError("formula references an unavailable pricing input")
                rate = self._decimal(component.get("unit_price"), "unit_price")
                total += pricing_inputs[input_name] * rate
            total = total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        elif pricing_type in {"starting_price", "range"}:
            automatic = quoting.get("automatic_quote_amount")
            if automatic is None:
                return PricingDecision(
                    None,
                    None,
                    None,
                    (),
                    True,
                    basis,
                    "Configured pricing is non-final and requires human approval",
                )
            total = self._decimal(automatic, "automatic_quote_amount")
            if pricing_type == "starting_price":
                minimum = self._decimal(quoting.get("starting_price"), "starting_price")
                if total < minimum:
                    raise ValueError("automatic quote amount is below the starting price")
            else:
                lower = self._decimal(quoting.get("range_min"), "range_min")
                upper = self._decimal(quoting.get("range_max"), "range_max")
                if not lower <= total <= upper:
                    raise ValueError("automatic quote amount is outside the configured range")
        else:
            raise ValueError("unsupported deterministic pricing type")
        assert total is not None
        require_money(total, "quote total")
        threshold_value = quoting.get("human_approval_threshold")
        threshold = (
            self._decimal(threshold_value, "human_approval_threshold")
            if threshold_value is not None
            else None
        )
        automatic_allowed = quoting.get("automatic_quote_allowed")
        if not isinstance(automatic_allowed, bool):
            raise ValueError("automatic_quote_allowed must be configured as a boolean")
        requires_human = not automatic_allowed or (
            threshold is not None and total > threshold
        )
        line = QuoteLine(
            line_id="service",
            description=str(service["name"]),
            quantity=Decimal("1"),
            unit_amount=total,
            line_total=total,
        )
        basis["currency"] = currency
        return PricingDecision(
            line,
            total,
            total,
            (),
            requires_human,
            basis,
            "Price requires human approval" if requires_human else "Price calculated",
        )

    @staticmethod
    def _decimal(value: object, field_name: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field_name} must be a decimal amount") from exc
        if not result.is_finite() or result < 0:
            raise ValueError(f"{field_name} must be finite and nonnegative")
        require_money(result, field_name)
        return result.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def payment_amount(total: Decimal, payment: Mapping[str, Any]) -> tuple[Decimal, str] | None:
    """Return a deterministic payment amount and DEPOSIT/FINAL type, if required."""

    require_money(total, "payment total")
    if total == Decimal("0.00"):
        return None
    deposit = payment.get("deposit", {})
    if not isinstance(deposit, Mapping):
        raise ValueError("payment.deposit must be an object")
    if deposit.get("required", False):
        deposit_type = deposit.get("type", "percentage")
        if deposit_type == "percentage":
            percentage = DeterministicPricingEngine._decimal(
                deposit.get("percentage"), "deposit percentage"
            )
            if not Decimal("0") < percentage <= Decimal("100"):
                raise ValueError("deposit percentage must be greater than 0 and at most 100")
            amount = (total * percentage / Decimal("100")).quantize(
                MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
        elif deposit_type == "fixed":
            amount = DeterministicPricingEngine._decimal(
                deposit.get("fixed_amount"), "deposit fixed_amount"
            )
            if amount <= 0:
                raise ValueError("fixed deposit must be greater than zero")
            if amount > total:
                raise ValueError("fixed deposit must not exceed the commercial total")
        else:
            raise ValueError("unsupported deposit type")
        require_money(amount, "deposit amount")
        if amount <= 0:
            raise ValueError("required deposit must round to more than zero")
        return amount, "DEPOSIT"
    if payment.get("timing") in {"before_booking", "before_service"}:
        return total, "FINAL"
    return None
