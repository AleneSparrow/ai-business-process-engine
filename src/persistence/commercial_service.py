"""Transactional commercial workflow after deterministic qualification."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, MutableMapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.domain.commercial import (
    Booking,
    BookingRequest,
    BookingStatus,
    CommercialPath,
    CommercialResponse,
    PaymentRequest,
    PaymentStatus,
    PaymentType,
    Quote,
    QuoteStatus,
    TimeSlot,
)
from src.domain.events import EventType
from src.domain.models import DecisionType, Lead, ProcessCase, ProcessEvent
from src.domain.states import ProcessState
from src.engine.commercial import (
    CommercialPathSelector,
    DeterministicAvailabilityEngine,
    DeterministicPricingEngine,
    DeterministicSlotPreferenceInterpreter,
    find_service,
    payment_amount,
)
from src.engine.decision_router import DecisionRequest
from src.engine.process_engine import ProcessEngine

from .repositories import UnitOfWork


# TEMPORARY diagnostic logging (2026-08-17): tracing the very first live use
# of the booking commercial path (CommercialPathSelector/_propose_slots) now
# that Settings can turn it on. Local helper for the same reason as
# src/ai/adapters.py and src/engine/qualification_service.py: avoids a
# src.persistence -> src.api dependency that risks a circular import.
_LOGGER = logging.getLogger("uvicorn.error")


def _log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"event": event, **{key: value for key, value in fields.items() if value is not None}}
    _LOGGER.log(level, json.dumps(payload, separators=(",", ":"), default=str))


UTC = timezone.utc
_ACTIVE_BOOKING_STATUSES = {
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.RESCHEDULED,
}
_NUMBER = re.compile(r"(?<![\w.])(?:\d+(?:\.\d{1,3})?)(?![\w.])")


class CommercialWorkflowService:
    """Executes only Business-DNA-authorized booking, quote, and payment preparation."""

    def __init__(
        self,
        *,
        path_selector: CommercialPathSelector | None = None,
        availability: DeterministicAvailabilityEngine | None = None,
        slot_interpreter: DeterministicSlotPreferenceInterpreter | None = None,
        pricing: DeterministicPricingEngine | None = None,
        process_engine: ProcessEngine | None = None,
    ) -> None:
        self.path_selector = path_selector or CommercialPathSelector()
        self.availability = availability or DeterministicAvailabilityEngine()
        self.slot_interpreter = slot_interpreter or DeterministicSlotPreferenceInterpreter()
        self.pricing = pricing or DeterministicPricingEngine()
        self.process_engine = process_engine or ProcessEngine()

    def initialize(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        business_dna: Mapping[str, Any],
        conversation_metadata: MutableMapping[str, Any],
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        self._require_utc(occurred_at)
        if case.current_state is not ProcessState.QUALIFIED:
            raise ValueError("commercial initialization requires a QUALIFIED case")
        commercial = self._commercial_metadata(conversation_metadata)
        existing_mode = commercial.get("mode")
        if existing_mode == "awaiting_slot":
            return self._slot_response(case, self._stored_slots(commercial))
        if existing_mode == "awaiting_pricing_input":
            return self._pricing_question_response(case, business_dna, commercial)
        if existing_mode == "direct_next_step":
            return CommercialResponse(
                str(commercial["message"]),
                "direct_next_step",
                case.current_state.value,
            )

        service_id = self._service_id(case)
        try:
            path = self.path_selector.select(business_dna, service_id)
        except ValueError as exc:
            # TEMPORARY diagnostic logging (2026-08-17): str(exc) here is
            # always one of this codebase's own fixed messages (see
            # CommercialPathSelector.select / find_service), never customer
            # content -- safe to log verbatim.
            _log_event(
                logging.INFO,
                "commercial_path_selection_failed_diagnostic",
                service_id=service_id,
                reason=str(exc),
            )
            return self._escalate(
                uow,
                case,
                business_dna,
                ProcessState.BOOKED,
                occurred_at,
                "Commercial path configuration requires human review",
            )
        _log_event(
            logging.INFO,
            "commercial_path_selected_diagnostic",
            service_id=service_id,
            path=path.value,
        )
        commercial.clear()
        commercial.update({"path": path.value, "service_id": service_id})
        self._audit(
            uow,
            case,
            EventType.COMMERCIAL_PATH_SELECTED,
            occurred_at,
            {"service_id": service_id, "path": path.value},
        )
        if path is CommercialPath.BOOKING:
            return self._propose_slots(
                uow, case, business_dna, commercial, occurred_at=occurred_at
            )
        if path is CommercialPath.QUOTE:
            return self._prepare_quote(
                uow, case, business_dna, commercial, occurred_at=occurred_at
            )
        if path is CommercialPath.DIRECT_NEXT_STEP:
            service = find_service(business_dna, service_id)
            message = service.get("direct_next_step_message")
            if not isinstance(message, str) or not message.strip():
                return self._escalate(
                    uow,
                    case,
                    business_dna,
                    ProcessState.BOOKED,
                    occurred_at,
                    "Direct next-step message is not safely configured",
                )
            commercial.update({"mode": "direct_next_step", "message": message.strip()})
            return CommercialResponse(
                message.strip(), "direct_next_step", case.current_state.value
            )
        return self._escalate(
            uow,
            case,
            business_dna,
            ProcessState.QUOTED,
            occurred_at,
            "Business DNA requires human commercial review",
        )

    def handle_message(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        business_dna: Mapping[str, Any],
        conversation_metadata: MutableMapping[str, Any],
        customer_text: str,
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        self._require_utc(occurred_at)
        commercial = self._commercial_metadata(conversation_metadata)
        text = customer_text.strip().casefold()
        if case.current_state is ProcessState.QUALIFIED:
            if commercial.get("mode") == "awaiting_slot":
                return self._select_slot(
                    uow,
                    case,
                    business_dna,
                    commercial,
                    customer_text,
                    occurred_at=occurred_at,
                )
            if commercial.get("mode") == "awaiting_pricing_input":
                return self._record_pricing_input(
                    uow,
                    case,
                    business_dna,
                    commercial,
                    customer_text,
                    occurred_at=occurred_at,
                )
            return self.initialize(
                uow,
                case,
                business_dna,
                conversation_metadata,
                occurred_at=occurred_at,
            )
        if case.current_state is ProcessState.QUOTED:
            return self._handle_quote(
                uow, case, business_dna, commercial, text, occurred_at=occurred_at
            )
        if case.current_state is ProcessState.BOOKED:
            if commercial.get("mode") == "awaiting_reschedule_slot":
                return self._select_reschedule_slot(
                    uow,
                    case,
                    business_dna,
                    commercial,
                    customer_text,
                    occurred_at=occurred_at,
                )
            if self._has_word(text, "cancel", "cancellation"):
                return self._cancel_booking(
                    uow, case, business_dna, occurred_at=occurred_at
                )
            if self._has_word(text, "reschedule", "change", "move"):
                return self._propose_reschedule(
                    uow,
                    case,
                    business_dna,
                    commercial,
                    occurred_at=occurred_at,
                )
            booking = uow.bookings.get_for_case(case.business_id, case.case_id)
            if booking is None:
                raise RuntimeError("BOOKED case has no tenant booking")
            return CommercialResponse(
                self._booking_confirmation(booking),
                "booking_already_confirmed",
                case.current_state.value,
                booking_id=booking.booking_id,
            )
        if case.current_state is ProcessState.WON:
            payment = uow.payment_requests.get_for_case_type(
                case.business_id, case.case_id, PaymentType.DEPOSIT
            ) or uow.payment_requests.get_for_case_type(
                case.business_id, case.case_id, PaymentType.FINAL
            )
            message = (
                "Your payment request is ready. No payment has been collected by this system."
                if payment is not None
                else "Your quote is accepted. The business will coordinate the next step."
            )
            return CommercialResponse(
                message,
                "commercial_won",
                case.current_state.value,
                payment_request_id=(payment.payment_request_id if payment else None),
            )
        raise ValueError(f"case state is not autonomous for commerce: {case.current_state.value}")

    def expire_due_items(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        *,
        occurred_at: datetime,
    ) -> None:
        """Lazily persist expirations without a background worker."""
        self._require_utc(occurred_at)
        quote = uow.quotes.get_for_case(case.business_id, case.case_id, for_update=True)
        if (
            quote is not None
            and quote.status is QuoteStatus.PRESENTED
            and quote.valid_until <= occurred_at
        ):
            expected = quote.version
            quote.change_status(QuoteStatus.EXPIRED, occurred_at)
            uow.quotes.save(quote, expected)
            self._audit(
                uow, case, EventType.QUOTE_EXPIRED, occurred_at, {"quote_id": quote.quote_id}
            )
            if case.current_state is ProcessState.QUOTED:
                self._transition(
                    uow, case, ProcessState.LOST, occurred_at, "Quote expired"
                )
        for payment_type in PaymentType:
            payment = uow.payment_requests.get_for_case_type(
                case.business_id, case.case_id, payment_type, for_update=True
            )
            if (
                payment is not None
                and payment.status in {
                    PaymentStatus.PENDING,
                    PaymentStatus.READY,
                    PaymentStatus.FAILED,
                }
                and payment.expires_at <= occurred_at
            ):
                expected = payment.version
                payment.change_status(PaymentStatus.EXPIRED, occurred_at)
                uow.payment_requests.save(payment, expected)
                self._audit(
                    uow,
                    case,
                    EventType.PAYMENT_REQUEST_EXPIRED,
                    occurred_at,
                    {"payment_request_id": payment.payment_request_id},
                )

    def get_proposed_slots(
        self, case: ProcessCase, *, occurred_at: datetime
    ) -> tuple[TimeSlot, ...]:
        """Read-only view of the currently valid, not-yet-selected slot
        proposal for this case (if any). Used by the public conversation API
        (see ConversationService.get_commercial) to render clickable slot
        options in the customer-facing widget -- purely a projection of the
        same `commercial` metadata `_propose_slots`/`_select_slot` already
        read and write; never mutates anything, so it's safe to call outside
        a transaction."""
        self._require_utc(occurred_at)
        commercial = case.metadata.get("commercial")
        if not isinstance(commercial, Mapping):
            return ()
        if commercial.get("mode") not in {"awaiting_slot", "awaiting_reschedule_slot"}:
            return ()
        return self._valid_stored_slots(commercial, occurred_at)

    def _propose_slots(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        *,
        occurred_at: datetime,
        exclude_booking_id: str | None = None,
        reschedule: bool = False,
    ) -> CommercialResponse:
        booking_config = self._mapping(dna.get("booking"), "booking")
        minimum_notice = self._bounded_int(
            booking_config.get("minimum_notice_minutes"),
            "minimum_notice_minutes",
            0,
            525_600,
        )
        maximum_advance = self._bounded_int(
            booking_config.get("maximum_advance_days"),
            "maximum_advance_days",
            1,
            730,
        )
        maximum_slots = self._bounded_int(
            booking_config.get("proposal_count", 3), "proposal_count", 1, 10
        )
        earliest = occurred_at + timedelta(minutes=minimum_notice)
        latest = occurred_at + timedelta(days=maximum_advance)
        service_id = self._service_id(case)
        service = find_service(dna, service_id)
        duration = self._bounded_int(
            booking_config.get("appointment_duration_minutes", service["duration_minutes"]),
            "appointment_duration_minutes",
            1,
            10_080,
        )
        buffer_minutes = self._bounded_int(
            booking_config.get("buffer_before_minutes", 0),
            "buffer_before_minutes",
            0,
            1_440,
        ) + self._bounded_int(
            booking_config.get("buffer_after_minutes", 0),
            "buffer_after_minutes",
            0,
            1_440,
        )
        existing = uow.bookings.list_overlapping(
            case.business_id,
            service_id,
            earliest - timedelta(minutes=buffer_minutes),
            latest + timedelta(minutes=duration + buffer_minutes),
            exclude_booking_id=exclude_booking_id,
        )
        request = BookingRequest(
            case.business_id,
            case.case_id,
            case.lead.lead_id,
            service_id,
            earliest,
            latest,
            maximum_slots,
        )
        slots = self.availability.available_slots(
            request, dna, existing, now=occurred_at
        )
        # TEMPORARY diagnostic logging (2026-08-17): config shape only
        # (no customer content) -- for tracing the very first live use of
        # the booking commercial path now that Settings can turn it on.
        booking_cfg = dna.get("booking")
        _log_event(
            logging.INFO,
            "slots_computed_diagnostic",
            service_id=service_id,
            slot_count=len(slots),
            earliest=earliest,
            latest=latest,
            existing_bookings=len(existing),
            booking_enabled=bool(booking_cfg.get("enabled")) if isinstance(booking_cfg, Mapping) else None,
            booking_timezone=booking_cfg.get("timezone") if isinstance(booking_cfg, Mapping) else None,
            allowed_days=booking_cfg.get("allowed_days") if isinstance(booking_cfg, Mapping) else None,
            business_hours_days=sorted(dna.get("business_hours", {}).keys()) if isinstance(dna.get("business_hours"), Mapping) else None,
        )
        self._audit(
            uow,
            case,
            EventType.AVAILABILITY_CALCULATED,
            occurred_at,
            {
                "service_id": service_id,
                "available_slot_count": len(slots),
                "reschedule": reschedule,
            },
        )
        if not slots:
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.BOOKED,
                occurred_at,
                "No deterministic availability is currently configured",
            )
        ttl = self._bounded_int(
            booking_config.get("proposal_ttl_minutes", 30),
            "proposal_ttl_minutes",
            1,
            1_440,
        )
        commercial.update({
            "mode": "awaiting_reschedule_slot" if reschedule else "awaiting_slot",
            "service_id": service_id,
            "slots": [self._serialize_slot(slot) for slot in slots],
            "slots_expires_at": (occurred_at + timedelta(minutes=ttl)).isoformat(),
        })
        self._audit(
            uow,
            case,
            EventType.SLOTS_PROPOSED,
            occurred_at,
            {
                "service_id": service_id,
                "slots": [
                    {"slot_id": slot.slot_id, "start_at": slot.start_at.isoformat()}
                    for slot in slots
                ],
                "reschedule": reschedule,
            },
        )
        return self._slot_response(case, slots, reschedule=reschedule)

    def _select_slot(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        customer_text: str,
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        slots = self._valid_stored_slots(commercial, occurred_at)
        if not slots:
            return self._propose_slots(
                uow, case, dna, commercial, occurred_at=occurred_at
            )
        preference = self.slot_interpreter.interpret(
            customer_text, slots, now=occurred_at
        )
        if preference.selected is None:
            if preference.candidates:
                return CommercialResponse(
                    "I found more than one matching option. Please reply with its option number.",
                    "slot_ambiguous",
                    case.current_state.value,
                )
            return CommercialResponse(
                "Please choose one of the proposed times by replying with its option number.",
                "slot_not_selected",
                case.current_state.value,
            )
        slot = preference.selected
        self._audit(
            uow,
            case,
            EventType.SLOT_SELECTED,
            occurred_at,
            {"slot_id": slot.slot_id, "start_at": slot.start_at.isoformat()},
        )
        existing_for_case = uow.bookings.get_for_case(
            case.business_id, case.case_id, for_update=True
        )
        if existing_for_case is not None:
            persisted_case = uow.cases.get(case.business_id, case.case_id)
            current = persisted_case.current_state if persisted_case else case.current_state
            return CommercialResponse(
                self._booking_confirmation(existing_for_case),
                "booking_duplicate",
                current.value,
                booking_id=existing_for_case.booking_id,
            )
        uow.bookings.lock_slot(case.business_id, self._service_id(case), slot.start_at)
        existing_for_case = uow.bookings.get_for_case(
            case.business_id, case.case_id, for_update=True
        )
        if existing_for_case is not None:
            persisted_case = uow.cases.get(case.business_id, case.case_id)
            current = persisted_case.current_state if persisted_case else ProcessState.BOOKED
            return CommercialResponse(
                self._booking_confirmation(existing_for_case),
                "booking_duplicate",
                current.value,
                booking_id=existing_for_case.booking_id,
            )
        if not self._slot_has_capacity(uow, case, dna, slot):
            return self._propose_slots(
                uow, case, dna, commercial, occurred_at=occurred_at
            )
        commercial_total = self._service_price(dna, self._service_id(case))
        if commercial_total is None and self._payment_required(dna):
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.BOOKED,
                occurred_at,
                "Required payment amount is not deterministically configured",
            )
        booking = Booking(
            booking_id=str(uuid4()),
            business_id=case.business_id,
            case_id=case.case_id,
            lead_id=case.lead.lead_id,
            service_id=self._service_id(case),
            start_at=slot.start_at,
            end_at=slot.end_at,
            timezone=slot.timezone,
            status=BookingStatus.CONFIRMED,
            created_at=occurred_at,
            updated_at=occurred_at,
            metadata={"slot_id": slot.slot_id},
        )
        uow.bookings.add(booking)
        self._audit(
            uow,
            case,
            EventType.BOOKING_CREATED,
            occurred_at,
            {
                "booking_id": booking.booking_id,
                "service_id": booking.service_id,
                "start_at": booking.start_at.isoformat(),
                "end_at": booking.end_at.isoformat(),
                "timezone": booking.timezone,
            },
        )
        self._transition(
            uow,
            case,
            ProcessState.BOOKED,
            occurred_at,
            "Deterministic booking was confirmed",
        )
        payment = self._prepare_payment(
            uow,
            case,
            dna,
            commercial_total,
            occurred_at,
            booking_id=booking.booking_id,
        )
        commercial.clear()
        commercial.update({"path": CommercialPath.BOOKING.value, "mode": "booked"})
        if payment is not None and payment.status is PaymentStatus.PENDING:
            escalation = self._escalate(
                uow,
                case,
                dna,
                ProcessState.FOLLOW_UP,
                occurred_at,
                "Payment policy requires human approval",
            )
            return CommercialResponse(
                escalation.message_text,
                escalation.reason,
                escalation.current_state,
                True,
                booking_id=booking.booking_id,
                payment_request_id=payment.payment_request_id,
            )
        message = self._booking_confirmation(booking)
        if payment is not None:
            message += " A payment link will be sent next; payment integration is not connected."
        return CommercialResponse(
            message,
            "booking_confirmed",
            case.current_state.value,
            booking_id=booking.booking_id,
            payment_request_id=(payment.payment_request_id if payment else None),
        )

    def _prepare_quote(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        service = find_service(dna, self._service_id(case))
        inputs = self._pricing_inputs(case)
        currency = str(dna["business"]["currency"])
        decision = self.pricing.calculate(service, currency, inputs)
        if decision.missing_inputs:
            commercial.update({
                "mode": "awaiting_pricing_input",
                "missing_pricing_inputs": list(decision.missing_inputs),
            })
            return self._pricing_question_response(case, dna, commercial)
        quote = uow.quotes.get_for_case(case.business_id, case.case_id, for_update=True)
        if quote is None:
            if decision.line is None or decision.subtotal is None or decision.total is None:
                return self._escalate(
                    uow,
                    case,
                    dna,
                    ProcessState.QUOTED,
                    occurred_at,
                    decision.reason,
                )
            quoting = self._mapping(service.get("quoting"), "service.quoting")
            expiry_days = self._bounded_int(
                quoting.get(
                    "quote_validity_days",
                    self._mapping(dna.get("sales"), "sales").get("quote_expiry_days"),
                ),
                "quote_expiry_days",
                1,
                365,
            )
            quote = Quote(
                quote_id=str(uuid4()),
                business_id=case.business_id,
                case_id=case.case_id,
                lead_id=case.lead.lead_id,
                service_id=self._service_id(case),
                currency=currency,
                subtotal=decision.subtotal,
                total=decision.total,
                valid_until=occurred_at + timedelta(days=expiry_days),
                status=QuoteStatus.DRAFT,
                created_at=occurred_at,
                updated_at=occurred_at,
                pricing_basis=dict(decision.pricing_basis),
                lines=(decision.line,),
            )
            uow.quotes.add(quote)
            self._audit(
                uow,
                case,
                EventType.QUOTE_CALCULATED,
                occurred_at,
                {
                    "quote_id": quote.quote_id,
                    "service_id": quote.service_id,
                    "currency": quote.currency,
                    "total": str(quote.total),
                    "requires_human": decision.requires_human,
                },
            )
        if decision.requires_human:
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.QUOTED,
                occurred_at,
                decision.reason,
            )
        if quote.status is QuoteStatus.DRAFT:
            expected = quote.version
            quote.change_status(QuoteStatus.PRESENTED, occurred_at)
            uow.quotes.save(quote, expected)
            self._audit(
                uow,
                case,
                EventType.QUOTE_PRESENTED,
                occurred_at,
                {"quote_id": quote.quote_id, "valid_until": quote.valid_until.isoformat()},
            )
        self._transition(
            uow,
            case,
            ProcessState.QUOTED,
            occurred_at,
            "Deterministic quote was presented",
        )
        commercial.clear()
        commercial.update({"path": CommercialPath.QUOTE.value, "mode": "quote_presented"})
        return CommercialResponse(
            self._quote_message(quote),
            "quote_presented",
            case.current_state.value,
            quote_id=quote.quote_id,
        )

    def _record_pricing_input(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        customer_text: str,
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        missing = commercial.get("missing_pricing_inputs", [])
        if not isinstance(missing, list) or not missing:
            return self._prepare_quote(
                uow, case, dna, commercial, occurred_at=occurred_at
            )
        matches = _NUMBER.findall(customer_text.replace(",", ""))
        if len(matches) != 1:
            return CommercialResponse(
                "Please provide one numeric value for the requested pricing detail.",
                "pricing_input_invalid",
                case.current_state.value,
            )
        try:
            value = Decimal(matches[0])
        except InvalidOperation:
            value = Decimal("NaN")
        if not value.is_finite() or value < 0:
            return CommercialResponse(
                "Please provide a non-negative numeric value for the requested pricing detail.",
                "pricing_input_invalid",
                case.current_state.value,
            )
        input_name = str(missing[0])
        inputs = {key: str(item) for key, item in self._pricing_inputs(case).items()}
        inputs[input_name] = str(value)
        attributes = dict(case.lead.attributes)
        attributes["pricing_inputs"] = inputs
        updated_lead = Lead(
            case.lead.lead_id,
            case.lead.name,
            case.lead.email,
            case.lead.phone,
            attributes,
        )
        case.update_lead(updated_lead)
        uow.leads.save(case.business_id, updated_lead, occurred_at)
        self._audit(
            uow,
            case,
            EventType.PRICING_INPUT_RECORDED,
            occurred_at,
            {"input": input_name, "value": str(value)},
        )
        return self._prepare_quote(
            uow, case, dna, commercial, occurred_at=occurred_at
        )

    def _handle_quote(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        text: str,
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        quote = uow.quotes.get_for_case(case.business_id, case.case_id, for_update=True)
        if quote is None:
            raise RuntimeError("QUOTED case has no tenant quote")
        if quote.status is QuoteStatus.ACCEPTED:
            persisted_case = uow.cases.get(case.business_id, case.case_id)
            current = persisted_case.current_state if persisted_case is not None else ProcessState.WON
            payment = uow.payment_requests.get_for_case_type(
                case.business_id, case.case_id, PaymentType.DEPOSIT
            ) or uow.payment_requests.get_for_case_type(
                case.business_id, case.case_id, PaymentType.FINAL
            )
            return CommercialResponse(
                "Thank you — your quote was already accepted.",
                "quote_acceptance_duplicate",
                current.value,
                quote_id=quote.quote_id,
                payment_request_id=(payment.payment_request_id if payment else None),
            )
        if quote.status in {QuoteStatus.REJECTED, QuoteStatus.EXPIRED, QuoteStatus.CANCELLED}:
            persisted_case = uow.cases.get(case.business_id, case.case_id)
            current = persisted_case.current_state if persisted_case is not None else ProcessState.LOST
            return CommercialResponse(
                "This quote is no longer active.",
                "quote_inactive",
                current.value,
                quote_id=quote.quote_id,
            )
        if quote.status is QuoteStatus.PRESENTED and quote.valid_until <= occurred_at:
            expected = quote.version
            quote.change_status(QuoteStatus.EXPIRED, occurred_at)
            uow.quotes.save(quote, expected)
            self._audit(
                uow, case, EventType.QUOTE_EXPIRED, occurred_at, {"quote_id": quote.quote_id}
            )
            self._transition(
                uow, case, ProcessState.LOST, occurred_at, "Quote expired"
            )
            return CommercialResponse(
                "That quote has expired. Please contact the business for a new review.",
                "quote_expired",
                case.current_state.value,
                quote_id=quote.quote_id,
            )
        discount_terms = ("discount", "cheaper", "lower price", "negotiate")
        if any(term in text for term in discount_terms):
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.FOLLOW_UP,
                occurred_at,
                "Customer requested a price exception",
            )
        accepted = self._has_word(text, "accept", "accepted", "yes", "approve", "proceed")
        rejected = (
            self._has_word(text, "reject", "decline")
            or text in {"no", "no thanks", "no thank you"}
            or "too expensive" in text
        )
        if accepted == rejected:
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.FOLLOW_UP,
                occurred_at,
                "Quote acceptance or rejection is ambiguous",
            )
        expected = quote.version
        if accepted:
            quote.change_status(QuoteStatus.ACCEPTED, occurred_at)
            uow.quotes.save(quote, expected)
            self._audit(
                uow, case, EventType.QUOTE_ACCEPTED, occurred_at, {"quote_id": quote.quote_id}
            )
            self._transition(
                uow, case, ProcessState.FOLLOW_UP, occurred_at, "Quote accepted"
            )
            self._transition(
                uow, case, ProcessState.WON, occurred_at, "Commercial outcome won"
            )
            payment = self._prepare_payment(
                uow,
                case,
                dna,
                quote.total,
                occurred_at,
                quote_id=quote.quote_id,
            )
            commercial["mode"] = "quote_accepted"
            if payment is not None and payment.status is PaymentStatus.PENDING:
                escalation = self._escalate(
                    uow,
                    case,
                    dna,
                    ProcessState.PAID,
                    occurred_at,
                    "Payment policy requires human approval",
                )
                return CommercialResponse(
                    escalation.message_text,
                    escalation.reason,
                    escalation.current_state,
                    True,
                    quote_id=quote.quote_id,
                    payment_request_id=payment.payment_request_id,
                )
            message = "Thank you — your quote is accepted. The business will coordinate the next step."
            if payment is not None:
                message += " A payment link will be sent next; payment integration is not connected."
            return CommercialResponse(
                message,
                "quote_accepted",
                case.current_state.value,
                quote_id=quote.quote_id,
                payment_request_id=(payment.payment_request_id if payment else None),
            )
        quote.change_status(QuoteStatus.REJECTED, occurred_at)
        uow.quotes.save(quote, expected)
        self._audit(
            uow, case, EventType.QUOTE_REJECTED, occurred_at, {"quote_id": quote.quote_id}
        )
        self._transition(uow, case, ProcessState.LOST, occurred_at, "Quote declined")
        commercial["mode"] = "quote_rejected"
        return CommercialResponse(
            "Understood — the quote was declined. No payment was requested.",
            "quote_rejected",
            case.current_state.value,
            quote_id=quote.quote_id,
        )

    def _propose_reschedule(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        booking = uow.bookings.get_for_case(
            case.business_id, case.case_id, for_update=True
        )
        if booking is None or booking.status not in _ACTIVE_BOOKING_STATUSES:
            raise RuntimeError("BOOKED case has no active tenant booking")
        policy = self._mapping(
            self._mapping(dna.get("booking"), "booking").get("rescheduling", {}),
            "booking.rescheduling",
        )
        if not policy.get("allowed", False) or not self._notice_satisfied(
            booking, policy, occurred_at
        ):
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.FOLLOW_UP,
                occurred_at,
                "Rescheduling policy requires human review",
            )
        return self._propose_slots(
            uow,
            case,
            dna,
            commercial,
            occurred_at=occurred_at,
            exclude_booking_id=booking.booking_id,
            reschedule=True,
        )

    def _select_reschedule_slot(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: MutableMapping[str, Any],
        customer_text: str,
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        slots = self._valid_stored_slots(commercial, occurred_at)
        booking = uow.bookings.get_for_case(
            case.business_id, case.case_id, for_update=True
        )
        if booking is None or booking.status not in _ACTIVE_BOOKING_STATUSES:
            raise RuntimeError("BOOKED case has no active tenant booking")
        if not slots:
            return self._propose_slots(
                uow,
                case,
                dna,
                commercial,
                occurred_at=occurred_at,
                exclude_booking_id=booking.booking_id,
                reschedule=True,
            )
        preference = self.slot_interpreter.interpret(customer_text, slots, now=occurred_at)
        if preference.selected is None:
            return CommercialResponse(
                "Please choose one of the proposed times by replying with its option number.",
                "reschedule_slot_not_selected",
                case.current_state.value,
                booking_id=booking.booking_id,
            )
        slot = preference.selected
        uow.bookings.lock_slot(case.business_id, booking.service_id, slot.start_at)
        if not self._slot_has_capacity(
            uow, case, dna, slot, exclude_booking_id=booking.booking_id
        ):
            return self._propose_slots(
                uow,
                case,
                dna,
                commercial,
                occurred_at=occurred_at,
                exclude_booking_id=booking.booking_id,
                reschedule=True,
            )
        previous_start = booking.start_at
        expected = booking.version
        booking.reschedule(slot, occurred_at)
        uow.bookings.save(booking, expected)
        self._audit(
            uow,
            case,
            EventType.BOOKING_RESCHEDULED,
            occurred_at,
            {
                "booking_id": booking.booking_id,
                "from_start_at": previous_start.isoformat(),
                "to_start_at": booking.start_at.isoformat(),
            },
        )
        commercial["mode"] = "booked"
        commercial.pop("slots", None)
        commercial.pop("slots_expires_at", None)
        return CommercialResponse(
            self._booking_confirmation(booking, prefix="Your appointment was rescheduled for"),
            "booking_rescheduled",
            case.current_state.value,
            booking_id=booking.booking_id,
        )

    def _cancel_booking(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        *,
        occurred_at: datetime,
    ) -> CommercialResponse:
        booking = uow.bookings.get_for_case(
            case.business_id, case.case_id, for_update=True
        )
        if booking is None or booking.status not in _ACTIVE_BOOKING_STATUSES:
            raise RuntimeError("BOOKED case has no active tenant booking")
        booking_config = self._mapping(dna.get("booking"), "booking")
        policy = self._mapping(
            booking_config.get(
                "cancellation",
                {
                    "allowed": True,
                    "minimum_notice_hours": booking_config.get(
                        "cancellation_notice_hours", 0
                    ),
                },
            ),
            "booking.cancellation",
        )
        if not policy.get("allowed", False) or not self._notice_satisfied(
            booking, policy, occurred_at
        ):
            return self._escalate(
                uow,
                case,
                dna,
                ProcessState.CANCELLED,
                occurred_at,
                "Cancellation policy requires human review",
            )
        expected = booking.version
        booking.cancel(occurred_at)
        uow.bookings.save(booking, expected)
        self._audit(
            uow,
            case,
            EventType.BOOKING_CANCELLED,
            occurred_at,
            {"booking_id": booking.booking_id},
        )
        for payment_type in PaymentType:
            payment = uow.payment_requests.get_for_case_type(
                case.business_id, case.case_id, payment_type, for_update=True
            )
            if payment is not None and payment.status in {
                PaymentStatus.PENDING,
                PaymentStatus.READY,
                PaymentStatus.FAILED,
            }:
                payment_expected = payment.version
                payment.change_status(PaymentStatus.CANCELLED, occurred_at)
                uow.payment_requests.save(payment, payment_expected)
        self._transition(
            uow, case, ProcessState.CANCELLED, occurred_at, "Booking cancelled"
        )
        return CommercialResponse(
            "Your booking was cancelled. No payment was collected by this system.",
            "booking_cancelled",
            case.current_state.value,
            booking_id=booking.booking_id,
        )

    def _slot_has_capacity(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        slot: TimeSlot,
        *,
        exclude_booking_id: str | None = None,
    ) -> bool:
        config = self._mapping(dna.get("booking"), "booking")
        before = self._bounded_int(
            config.get("buffer_before_minutes", 0), "buffer_before_minutes", 0, 1_440
        )
        after = self._bounded_int(
            config.get("buffer_after_minutes", 0), "buffer_after_minutes", 0, 1_440
        )
        bookings = uow.bookings.list_overlapping(
            case.business_id,
            self._service_id(case),
            slot.start_at - timedelta(minutes=before + after),
            slot.end_at + timedelta(minutes=before + after),
            exclude_booking_id=exclude_booking_id,
        )
        occupied = sum(
            self.availability._overlaps_with_buffers(
                slot.start_at,
                slot.end_at,
                booking.start_at,
                booking.end_at,
                before,
                after,
            )
            for booking in bookings
            if booking.status in _ACTIVE_BOOKING_STATUSES
        )
        return occupied < slot.capacity

    def _prepare_payment(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        total: Decimal | None,
        occurred_at: datetime,
        *,
        quote_id: str | None = None,
        booking_id: str | None = None,
    ) -> PaymentRequest | None:
        if total is None:
            return None
        config = self._mapping(dna.get("payment"), "payment")
        configured_currency = config.get("currency")
        business = self._mapping(dna.get("business"), "business")
        if not isinstance(configured_currency, str) or configured_currency != business.get(
            "currency"
        ):
            raise ValueError("payment currency must match the configured business currency")
        prepared = payment_amount(total, config)
        if prepared is None:
            return None
        amount, type_value = prepared
        payment_type = PaymentType(type_value)
        existing = uow.payment_requests.get_for_case_type(
            case.business_id, case.case_id, payment_type
        )
        if existing is not None:
            return existing
        expiry_hours = self._bounded_int(
            config.get("request_expiry_hours", 72), "request_expiry_hours", 1, 8_760
        )
        approval_threshold = DeterministicPricingEngine._decimal(
            config.get("human_approval_above"), "payment human_approval_above"
        )
        approval_required = total > approval_threshold
        payment = PaymentRequest(
            payment_request_id=str(uuid4()),
            business_id=case.business_id,
            case_id=case.case_id,
            quote_id=quote_id,
            booking_id=booking_id,
            amount=amount,
            currency=configured_currency,
            payment_type=payment_type,
            status=PaymentStatus.PENDING if approval_required else PaymentStatus.READY,
            created_at=occurred_at,
            updated_at=occurred_at,
            expires_at=occurred_at + timedelta(hours=expiry_hours),
            metadata={
                "provider_required": True,
                "collection_attempted": False,
                "human_approval_required": approval_required,
            },
        )
        uow.payment_requests.add(payment)
        self._audit(
            uow,
            case,
            EventType.PAYMENT_REQUEST_CREATED,
            occurred_at,
            {
                "payment_request_id": payment.payment_request_id,
                "payment_type": payment.payment_type.value,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "status": payment.status.value,
                "human_approval_required": approval_required,
            },
        )
        return payment

    def _escalate(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        dna: Mapping[str, Any],
        pending_target: ProcessState,
        occurred_at: datetime,
        reason: str,
    ) -> CommercialResponse:
        self._transition(
            uow,
            case,
            pending_target,
            occurred_at,
            reason,
            requires_human=True,
        )
        escalation = self._mapping(dna.get("human_escalation"), "human_escalation")
        message = escalation.get("customer_message")
        if not isinstance(message, str) or not message.strip():
            raise RuntimeError("Business DNA has no safe human escalation response")
        return CommercialResponse(
            message.strip(), reason, case.current_state.value, requires_human=True
        )

    def _transition(
        self,
        uow: UnitOfWork,
        case: ProcessCase,
        target: ProcessState,
        occurred_at: datetime,
        reason: str,
        *,
        requires_human: bool = False,
    ) -> None:
        expected = case.version
        existing_event_count = len(case.event_history)
        event = ProcessEvent(
            EventType.TRIGGER_RECEIVED,
            occurred_at=occurred_at,
            source="commercial_workflow",
            payload={"reason": reason, "requested_target": target.value},
        )
        request = DecisionRequest(
            DecisionType.HUMAN if requires_human else DecisionType.RULE,
            target,
        )
        self.process_engine.receive(case, event, request)
        uow.cases.save(case, expected)
        uow.events.add_many(
            case.business_id, case.case_id, case.event_history[existing_event_count:]
        )

    @staticmethod
    def _audit(
        uow: UnitOfWork,
        case: ProcessCase,
        event_type: EventType,
        occurred_at: datetime,
        payload: Mapping[str, Any],
    ) -> None:
        uow.events.add(
            case.business_id,
            case.case_id,
            ProcessEvent(
                event_type,
                occurred_at=occurred_at,
                source="commercial_workflow",
                payload=payload,
            ),
        )

    @staticmethod
    def _service_id(case: ProcessCase) -> str:
        value = case.lead.attributes.get("service_requested")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("qualified case has no service_requested")
        return value

    @staticmethod
    def _pricing_inputs(case: ProcessCase) -> dict[str, Decimal]:
        qualification_answers = case.lead.attributes.get("qualification_answers", {})
        raw = case.lead.attributes.get("pricing_inputs", {})
        if not isinstance(qualification_answers, Mapping):
            raise ValueError("lead qualification_answers must be an object")
        if not isinstance(raw, Mapping):
            raise ValueError("lead pricing_inputs must be an object")
        result: dict[str, Decimal] = {}
        # Numeric validated qualification answers may satisfy a pricing input;
        # unrelated boolean/text answers remain qualification facts only.
        for key, value in qualification_answers.items():
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, ValueError):
                continue
            if parsed.is_finite() and parsed >= 0:
                result[str(key)] = parsed
        # Values collected by the commercial dialogue override qualification
        # answers and are strict persisted pricing inputs.
        for key, value in raw.items():
            try:
                parsed = Decimal(str(value))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("stored pricing input is not a decimal") from exc
            if not parsed.is_finite() or parsed < 0:
                raise ValueError("stored pricing input must be finite and nonnegative")
            result[str(key)] = parsed
        return result

    @staticmethod
    def _service_price(dna: Mapping[str, Any], service_id: str) -> Decimal | None:
        pricing = find_service(dna, service_id).get("pricing", {})
        if not isinstance(pricing, Mapping) or pricing.get("model") != "fixed":
            return None
        return DeterministicPricingEngine._decimal(
            pricing.get("amount"), "service fixed price"
        )

    @classmethod
    def _payment_required(cls, dna: Mapping[str, Any]) -> bool:
        payment = cls._mapping(dna.get("payment"), "payment")
        deposit = cls._mapping(payment.get("deposit"), "payment.deposit")
        return bool(deposit.get("required", False)) or payment.get("timing") in {
            "before_booking",
            "before_service",
        }

    @staticmethod
    def _commercial_metadata(
        metadata: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        value = metadata.setdefault("commercial", {})
        if not isinstance(value, dict):
            raise ValueError("conversation commercial metadata must be an object")
        return value

    @staticmethod
    def _serialize_slot(slot: TimeSlot) -> dict[str, Any]:
        return {
            "slot_id": slot.slot_id,
            "start_at": slot.start_at.isoformat(),
            "end_at": slot.end_at.isoformat(),
            "timezone": slot.timezone,
            "capacity": slot.capacity,
        }

    @classmethod
    def _stored_slots(cls, commercial: Mapping[str, Any]) -> tuple[TimeSlot, ...]:
        raw_slots = commercial.get("slots", [])
        if not isinstance(raw_slots, list):
            raise ValueError("stored commercial slots must be an array")
        result: list[TimeSlot] = []
        for value in raw_slots:
            if not isinstance(value, Mapping):
                raise ValueError("stored commercial slot must be an object")
            result.append(TimeSlot(
                str(value["slot_id"]),
                datetime.fromisoformat(str(value["start_at"])),
                datetime.fromisoformat(str(value["end_at"])),
                str(value["timezone"]),
                int(value["capacity"]),
            ))
        return tuple(result)

    @classmethod
    def _valid_stored_slots(
        cls, commercial: Mapping[str, Any], occurred_at: datetime
    ) -> tuple[TimeSlot, ...]:
        expiry_value = commercial.get("slots_expires_at")
        if not isinstance(expiry_value, str):
            return ()
        expiry = datetime.fromisoformat(expiry_value)
        cls._require_utc(expiry)
        return cls._stored_slots(commercial) if expiry > occurred_at else ()

    @staticmethod
    def _slot_response(
        case: ProcessCase,
        slots: tuple[TimeSlot, ...],
        *,
        reschedule: bool = False,
    ) -> CommercialResponse:
        if not slots:
            raise ValueError("slot response requires at least one slot")
        options = []
        for index, slot in enumerate(slots, start=1):
            local = slot.start_at.astimezone(ZoneInfo(slot.timezone))
            options.append(f"{index}) {local.strftime('%A, %B %d at %I:%M %p %Z')}")
        lead_in = "Choose a new appointment time:" if reschedule else "Choose an appointment time:"
        return CommercialResponse(
            lead_in + "\n" + "\n".join(options),
            "reschedule_slots_proposed" if reschedule else "booking_slots_proposed",
            case.current_state.value,
        )

    @classmethod
    def _pricing_question_response(
        cls,
        case: ProcessCase,
        dna: Mapping[str, Any],
        commercial: Mapping[str, Any],
    ) -> CommercialResponse:
        missing = commercial.get("missing_pricing_inputs", [])
        if not isinstance(missing, list) or not missing:
            raise ValueError("missing pricing input metadata is invalid")
        service = find_service(dna, cls._service_id(case))
        quoting = cls._mapping(service.get("quoting"), "service.quoting")
        questions = cls._mapping(
            quoting.get("pricing_input_questions", {}), "pricing_input_questions"
        )
        question = questions.get(str(missing[0]))
        if not isinstance(question, str) or not question.strip():
            raise ValueError("required pricing input has no configured customer question")
        return CommercialResponse(
            question.strip(),
            "pricing_input_required",
            case.current_state.value,
        )

    @staticmethod
    def _quote_message(quote: Quote) -> str:
        description = ", ".join(line.description for line in quote.lines)
        return (
            f"Your quote for {description} is {quote.currency} {quote.total:.2f}, valid through "
            f"{quote.valid_until.date().isoformat()}. Reply accept or decline."
        )

    @staticmethod
    def _booking_confirmation(
        booking: Booking, *, prefix: str = "Your appointment is confirmed for"
    ) -> str:
        local = booking.start_at.astimezone(ZoneInfo(booking.timezone))
        return f"{prefix} {local.strftime('%A, %B %d at %I:%M %p %Z')}."

    @staticmethod
    def _notice_satisfied(
        booking: Booking, policy: Mapping[str, Any], occurred_at: datetime
    ) -> bool:
        hours = CommercialWorkflowService._bounded_int(
            policy.get("minimum_notice_hours", 0), "minimum_notice_hours", 0, 8_760
        )
        return booking.start_at - occurred_at >= timedelta(hours=hours)

    @staticmethod
    def _mapping(value: object, name: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{name} must be an object")
        return value

    @staticmethod
    def _bounded_int(value: object, name: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _has_word(text: str, *words: str) -> bool:
        return any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) for word in words)

    @staticmethod
    def _require_utc(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("commercial timestamps must use aware UTC")
