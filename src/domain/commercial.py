"""Commercial domain values for booking, quoting, and payment preparation."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text


MONEY_QUANTUM = Decimal("0.01")


def require_money(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be finite and nonnegative")
    if value != value.quantize(MONEY_QUANTUM):
        raise ValueError(f"{field_name} must have at most two decimal places")


def require_currency(value: str) -> None:
    if not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("currency must be a three-letter uppercase code")


def require_utc(value: datetime, field_name: str) -> None:
    _require_aware(value, field_name)
    if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be stored in UTC")


class CommercialPath(StrEnum):
    BOOKING = "booking"
    QUOTE = "quote"
    DIRECT_NEXT_STEP = "direct_next_step"
    HUMAN_REVIEW = "human_review"


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    COMPLETED = "COMPLETED"


class QuoteStatus(StrEnum):
    DRAFT = "DRAFT"
    PRESENTED = "PRESENTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PaymentType(StrEnum):
    DEPOSIT = "DEPOSIT"
    FINAL = "FINAL"


@dataclass(frozen=True, slots=True)
class AvailabilityWindow:
    start_at: datetime
    end_at: datetime
    timezone: str
    capacity: int = 1

    def __post_init__(self) -> None:
        require_utc(self.start_at, "start_at")
        require_utc(self.end_at, "end_at")
        _require_text(self.timezone, "timezone")
        if self.end_at <= self.start_at:
            raise ValueError("availability window must end after it starts")
        if self.capacity < 1:
            raise ValueError("availability capacity must be positive")


@dataclass(frozen=True, slots=True)
class TimeSlot:
    slot_id: str
    start_at: datetime
    end_at: datetime
    timezone: str
    capacity: int = 1

    def __post_init__(self) -> None:
        _require_text(self.slot_id, "slot_id")
        require_utc(self.start_at, "start_at")
        require_utc(self.end_at, "end_at")
        _require_text(self.timezone, "timezone")
        if self.end_at <= self.start_at:
            raise ValueError("time slot must end after it starts")
        if self.capacity < 1:
            raise ValueError("slot capacity must be positive")


@dataclass(frozen=True, slots=True)
class BookingRequest:
    business_id: str
    case_id: str
    lead_id: str
    service_id: str
    earliest_start: datetime
    latest_start: datetime
    maximum_slots: int = 3

    def __post_init__(self) -> None:
        for value, name in (
            (self.business_id, "business_id"),
            (self.case_id, "case_id"),
            (self.lead_id, "lead_id"),
            (self.service_id, "service_id"),
        ):
            _require_text(value, name)
        require_utc(self.earliest_start, "earliest_start")
        require_utc(self.latest_start, "latest_start")
        if self.latest_start <= self.earliest_start:
            raise ValueError("latest_start must be after earliest_start")
        if not 1 <= self.maximum_slots <= 10:
            raise ValueError("maximum_slots must be between 1 and 10")


@dataclass(slots=True)
class Booking:
    booking_id: str
    business_id: str
    case_id: str
    lead_id: str
    service_id: str
    start_at: datetime
    end_at: datetime
    timezone: str
    status: BookingStatus
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        for value, name in (
            (self.booking_id, "booking_id"),
            (self.business_id, "business_id"),
            (self.case_id, "case_id"),
            (self.lead_id, "lead_id"),
            (self.service_id, "service_id"),
            (self.timezone, "timezone"),
        ):
            _require_text(value, name)
        if not isinstance(self.status, BookingStatus):
            raise TypeError("status must be a BookingStatus")
        for value, name in (
            (self.start_at, "start_at"),
            (self.end_at, "end_at"),
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
        ):
            require_utc(value, name)
        if self.end_at <= self.start_at:
            raise ValueError("booking must end after it starts")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.version < 0:
            raise ValueError("version must not be negative")
        self.metadata = dict(self.metadata)

    def cancel(self, occurred_at: datetime) -> None:
        require_utc(occurred_at, "occurred_at")
        if self.status not in {
            BookingStatus.PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.RESCHEDULED,
        }:
            raise ValueError("booking cannot be cancelled from its current status")
        self.status = BookingStatus.CANCELLED
        self.updated_at = max(self.updated_at, occurred_at)

    def complete(self, occurred_at: datetime) -> None:
        require_utc(occurred_at, "occurred_at")
        if self.status not in {BookingStatus.CONFIRMED, BookingStatus.RESCHEDULED}:
            raise ValueError("booking cannot be completed from its current status")
        self.status = BookingStatus.COMPLETED
        self.updated_at = max(self.updated_at, occurred_at)

    def reschedule(self, slot: TimeSlot, occurred_at: datetime) -> None:
        require_utc(occurred_at, "occurred_at")
        if self.status not in {BookingStatus.CONFIRMED, BookingStatus.RESCHEDULED}:
            raise ValueError("booking cannot be rescheduled from its current status")
        self.start_at = slot.start_at
        self.end_at = slot.end_at
        self.timezone = slot.timezone
        self.status = BookingStatus.RESCHEDULED
        self.updated_at = max(self.updated_at, occurred_at)

    def mark_persisted(self, version: int) -> None:
        if version <= self.version:
            raise ValueError("persisted version must advance")
        self.version = version


@dataclass(frozen=True, slots=True)
class BookingResult:
    booking: Booking | None
    created: bool
    duplicate: bool
    reason: str

    def __post_init__(self) -> None:
        _require_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class QuoteLine:
    line_id: str
    description: str
    quantity: Decimal
    unit_amount: Decimal
    line_total: Decimal

    def __post_init__(self) -> None:
        _require_text(self.line_id, "line_id")
        _require_text(self.description, "description")
        if not isinstance(self.quantity, Decimal) or not self.quantity.is_finite():
            raise TypeError("quantity must be a finite Decimal")
        if self.quantity <= 0 or self.quantity.as_tuple().exponent < -3:
            raise ValueError("quantity must be positive with at most three decimal places")
        require_money(self.unit_amount, "unit_amount")
        require_money(self.line_total, "line_total")
        if (self.quantity * self.unit_amount).quantize(
            MONEY_QUANTUM, rounding=ROUND_HALF_UP
        ) != self.line_total:
            raise ValueError("line_total must equal quantity multiplied by unit_amount")


@dataclass(frozen=True, slots=True)
class QuoteRequest:
    business_id: str
    case_id: str
    lead_id: str
    service_id: str
    pricing_inputs: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.business_id, "business_id"),
            (self.case_id, "case_id"),
            (self.lead_id, "lead_id"),
            (self.service_id, "service_id"),
        ):
            _require_text(value, name)
        for key, value in self.pricing_inputs.items():
            _require_text(str(key), "pricing input name")
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("pricing inputs must be finite nonnegative Decimals")
        object.__setattr__(self, "pricing_inputs", _freeze(self.pricing_inputs))


@dataclass(slots=True)
class Quote:
    quote_id: str
    business_id: str
    case_id: str
    lead_id: str
    service_id: str
    currency: str
    subtotal: Decimal
    total: Decimal
    valid_until: datetime
    status: QuoteStatus
    created_at: datetime
    updated_at: datetime
    pricing_basis: dict[str, Any]
    lines: tuple[QuoteLine, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        for value, name in (
            (self.quote_id, "quote_id"),
            (self.business_id, "business_id"),
            (self.case_id, "case_id"),
            (self.lead_id, "lead_id"),
            (self.service_id, "service_id"),
        ):
            _require_text(value, name)
        require_currency(self.currency)
        require_money(self.subtotal, "subtotal")
        require_money(self.total, "total")
        if self.total < self.subtotal:
            raise ValueError("total must not be less than subtotal")
        if not isinstance(self.status, QuoteStatus):
            raise TypeError("status must be a QuoteStatus")
        for value, name in (
            (self.valid_until, "valid_until"),
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
        ):
            require_utc(value, name)
        if self.valid_until <= self.created_at:
            raise ValueError("quote validity must end after creation")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.lines and sum((line.line_total for line in self.lines), Decimal("0.00")) != self.subtotal:
            raise ValueError("quote line totals must equal subtotal")
        if self.version < 0:
            raise ValueError("version must not be negative")
        self.pricing_basis = dict(self.pricing_basis)
        self.lines = tuple(self.lines)
        self.metadata = dict(self.metadata)

    def change_status(self, status: QuoteStatus, occurred_at: datetime) -> None:
        require_utc(occurred_at, "occurred_at")
        allowed = {
            QuoteStatus.DRAFT: {QuoteStatus.PRESENTED, QuoteStatus.CANCELLED},
            QuoteStatus.PRESENTED: {
                QuoteStatus.ACCEPTED,
                QuoteStatus.REJECTED,
                QuoteStatus.EXPIRED,
                QuoteStatus.CANCELLED,
            },
            QuoteStatus.ACCEPTED: set(),
            QuoteStatus.REJECTED: set(),
            QuoteStatus.EXPIRED: set(),
            QuoteStatus.CANCELLED: set(),
        }
        if status is self.status:
            return
        if status not in allowed[self.status]:
            raise ValueError(f"invalid quote status transition: {self.status} -> {status}")
        self.status = status
        self.updated_at = max(self.updated_at, occurred_at)

    def mark_persisted(self, version: int) -> None:
        if version <= self.version:
            raise ValueError("persisted version must advance")
        self.version = version


@dataclass(frozen=True, slots=True)
class QuoteResult:
    quote: Quote | None
    missing_inputs: tuple[str, ...]
    requires_human: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_inputs", tuple(self.missing_inputs))
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(slots=True)
class PaymentRequest:
    payment_request_id: str
    business_id: str
    case_id: str
    amount: Decimal
    currency: str
    payment_type: PaymentType
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    quote_id: str | None = None
    booking_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        for value, name in (
            (self.payment_request_id, "payment_request_id"),
            (self.business_id, "business_id"),
            (self.case_id, "case_id"),
        ):
            _require_text(value, name)
        for value, name in ((self.quote_id, "quote_id"), (self.booking_id, "booking_id")):
            if value is not None:
                _require_text(value, name)
        require_money(self.amount, "amount")
        require_currency(self.currency)
        if not isinstance(self.payment_type, PaymentType):
            raise TypeError("payment_type must be a PaymentType")
        if not isinstance(self.status, PaymentStatus):
            raise TypeError("status must be a PaymentStatus")
        require_utc(self.created_at, "created_at")
        require_utc(self.updated_at, "updated_at")
        require_utc(self.expires_at, "expires_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")
        if self.expires_at <= self.created_at:
            raise ValueError("payment request must expire after creation")
        if self.version < 0:
            raise ValueError("version must not be negative")
        self.metadata = dict(self.metadata)

    def change_status(self, status: PaymentStatus, occurred_at: datetime) -> None:
        require_utc(occurred_at, "occurred_at")
        allowed = {
            PaymentStatus.PENDING: {
                PaymentStatus.READY,
                PaymentStatus.CANCELLED,
                PaymentStatus.EXPIRED,
            },
            PaymentStatus.READY: {
                PaymentStatus.PAID,
                PaymentStatus.FAILED,
                PaymentStatus.CANCELLED,
                PaymentStatus.EXPIRED,
            },
            PaymentStatus.FAILED: {
                PaymentStatus.READY,
                PaymentStatus.CANCELLED,
                PaymentStatus.EXPIRED,
            },
            PaymentStatus.PAID: set(),
            PaymentStatus.CANCELLED: set(),
            PaymentStatus.EXPIRED: set(),
        }
        if status is self.status:
            return
        if status not in allowed[self.status]:
            raise ValueError(f"invalid payment status transition: {self.status} -> {status}")
        self.status = status
        self.updated_at = max(self.updated_at, occurred_at)

    def mark_persisted(self, version: int) -> None:
        if version <= self.version:
            raise ValueError("persisted version must advance")
        self.version = version


@dataclass(frozen=True, slots=True)
class CommercialResponse:
    message_text: str
    reason: str
    current_state: str
    requires_human: bool = False
    booking_id: str | None = None
    quote_id: str | None = None
    payment_request_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.message_text, "message_text")
        _require_text(self.reason, "reason")
        _require_text(self.current_state, "current_state")
