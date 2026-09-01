import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.events import EventType
from src.domain.qualification import IncomingMessage, IntentResult, Urgency
from src.domain.states import ProcessState
from src.engine.intent_extractor import DeterministicIntentExtractor
from src.engine.lead_intake import LeadIntakeService
from src.engine.question_generator import DeterministicQuestionGenerator


ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 11, 8, 0, tzinfo=timezone.utc)


def business_dna() -> dict:
    with (ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        return json.load(file)


def message(
    external_message_id: str,
    *,
    name: str | None = "Ada",
    phone: str | None = "+1 312 555 0100",
    email: str | None = None,
    case_id: str | None = None,
) -> IncomingMessage:
    return IncomingMessage(
        business_id="acme-home-services",
        channel="sms",
        external_message_id=external_message_id,
        customer_name=name,
        phone=phone,
        email=email,
        raw_text="I need help",
        timestamp=NOW,
        case_id=case_id,
    )


def service_with(results: dict[str, IntentResult], dna: dict | None = None) -> LeadIntakeService:
    return LeadIntakeService(
        dna or business_dna(),
        DeterministicIntentExtractor(results),
        DeterministicQuestionGenerator(),
    )


def valid_intent(**changes: object) -> IntentResult:
    values = {
        "service_requested": "diagnostic-visit",
        "urgency": Urgency.NORMAL,
        "customer_location": "60601",
        "confidence": 0.95,
    }
    values.update(changes)
    return IntentResult(**values)  # type: ignore[arg-type]


def test_valid_service_area_and_information_becomes_qualified() -> None:
    intake = service_with({"msg-a": valid_intent()})

    result = intake.receive(message("msg-a"))

    assert result.current_state is ProcessState.QUALIFIED
    assert result.qualification.qualified
    assert result.qualification.booking_allowed
    assert result.response is None
    case = intake.get_case(result.case_id)
    changes = [event.payload["to"] for event in case.event_history if event.event_type is EventType.STATE_CHANGED]
    assert changes == ["CONTACTED", "QUALIFYING", "QUALIFIED"]


def test_missing_phone_remains_qualifying_and_generates_configured_question() -> None:
    intake = service_with({"msg-b": valid_intent()})

    result = intake.receive(message("msg-b", phone=None))

    assert result.current_state is ProcessState.QUALIFYING
    assert result.qualification.missing_fields == ("phone",)
    assert result.response is not None
    assert result.response.message_text == "What is the best phone number to reach you?"
    assert result.response.reason == "missing_information"


def test_service_then_name_and_phone_completes_qualification() -> None:
    """A normal follow-up must retain the service and area established on
    the first turn. This guards the live law-firm-shaped flow: service
    request, then a concise name-and-phone answer."""
    intake = service_with({
        "service-request": valid_intent(),
        "contact-details": IntentResult(confidence=0.95),
    })

    first = intake.receive(message("service-request", name=None, phone=None))
    second = intake.receive(message(
        "contact-details",
        name="Sarah Chen",
        phone="+1 312 555 0199",
        case_id=first.case_id,
    ))

    assert first.current_state is ProcessState.QUALIFYING
    assert first.qualification.missing_fields == ("name", "phone")
    assert second.current_state is ProcessState.QUALIFIED
    assert second.qualification.qualified
    assert not second.qualification.requires_human


def test_unsupported_service_is_lost() -> None:
    intake = service_with({"msg-c": valid_intent(service_requested="roof_replacement")})

    result = intake.receive(message("msg-c"))

    assert result.current_state is ProcessState.LOST
    assert "not offered" in result.qualification.reasons[0]
    assert result.response is not None
    assert result.response.reason == "not_qualified"


def test_outside_enforced_service_area_is_lost() -> None:
    intake = service_with({"msg-d": valid_intent(customer_location="99999")})

    result = intake.receive(message("msg-d"))

    assert result.current_state is ProcessState.LOST
    assert result.qualification.reasons == ("Customer is outside the configured service area",)


OUT_OF_AREA_TEXT = (
    "Sorry — that address is outside the area we currently serve. "
    "If you have another address nearby, send the ZIP code and we'll check it."
)


def _dna_with_out_of_area_message() -> dict:
    dna = business_dna()
    dna["qualification"]["lost_message_out_of_area"] = OUT_OF_AREA_TEXT
    return dna


def test_out_of_area_decline_says_it_is_about_the_area() -> None:
    """The only LOST reason a customer can act on gets its own wording.

    Live finding 2026-08-24 on production: a lead whose ZIP fell outside the
    configured service area was told "this request falls outside what we
    currently support" -- the same sentence a business gives for a service it
    does not offer. The engine knew the real reason deterministically and threw
    it away, so someone ten miles out never learned that a different address
    was all it took.
    """
    intake = service_with(
        {"msg-area": valid_intent(customer_location="99999")},
        dna=_dna_with_out_of_area_message(),
    )

    result = intake.receive(message("msg-area"))

    assert result.current_state is ProcessState.LOST
    assert result.response is not None
    assert result.response.message_text.startswith(OUT_OF_AREA_TEXT)


def test_other_lost_reasons_keep_the_general_decline() -> None:
    """Only the area reason is special-cased -- an unoffered service is not.

    Guards the obvious over-correction: telling someone who asked for a service
    the business does not provide to "send another ZIP code" would be worse
    than the generic sentence, not better.
    """
    intake = service_with(
        {"msg-svc": valid_intent(service_requested="roof_replacement")},
        dna=_dna_with_out_of_area_message(),
    )

    result = intake.receive(message("msg-svc"))

    assert result.current_state is ProcessState.LOST
    assert result.response is not None
    assert OUT_OF_AREA_TEXT not in result.response.message_text


def test_dna_without_the_new_field_falls_back_to_the_general_decline() -> None:
    """No migration needed: DNA predating the field must keep working.

    business_dna.example.json deliberately does NOT define
    lost_message_out_of_area, so this exercises the fallback path that every
    business created before 2026-08-25 takes.
    """
    dna = business_dna()
    assert "lost_message_out_of_area" not in dna["qualification"]

    intake = service_with({"msg-old": valid_intent(customer_location="99999")}, dna=dna)

    result = intake.receive(message("msg-old"))

    assert result.current_state is ProcessState.LOST
    assert result.response is not None
    assert result.response.message_text.startswith(dna["qualification"]["lost_message"])


def test_low_confidence_intent_requires_human() -> None:
    intake = service_with({"msg-e": valid_intent(confidence=0.2)})

    result = intake.receive(message("msg-e"))

    assert result.current_state is ProcessState.NEEDS_HUMAN
    assert result.qualification.requires_human
    assert result.response is not None and result.response.requires_human
    assert intake.get_case(result.case_id).pending_transition is ProcessState.QUALIFIED


def test_unintelligible_input_requests_clarification_without_escalation() -> None:
    """Live defect (2026-08-23): a customer message the AI could not
    interpret at all (e.g. "ропапа" in answer to a name/phone question) used
    to escalate straight to NEEDS_HUMAN. It must instead be treated like "no
    new information this turn" -- missing fields computed exactly as they
    would be for any other turn, not a hardcoded stand-in. Here the service
    was never established, so re-asking about it (among other missing
    fields) is correct."""
    intake = service_with({
        "msg-gibberish": IntentResult(
            confidence=0.95,
            requires_human=False,
            unintelligible=True,
        )
    })

    result = intake.receive(message("msg-gibberish"))

    assert result.current_state is ProcessState.QUALIFYING
    assert not result.qualification.requires_human
    assert result.qualification.missing_fields == ("service_address", "service_id")
    assert result.response is not None
    assert result.response.message_text == (
        "Sorry, I didn't quite catch that — What is the service ZIP code? Which service do you need?"
    )


def test_unintelligible_input_after_service_established_repeats_specific_missing_fields() -> None:
    """Live defect (2026-08-23): once the service is already established
    (from an earlier, understood message) an unintelligible follow-up must
    re-ask exactly what's still missing -- name and phone here -- not revert
    to the generic opening question about which service is needed. The
    wording must also acknowledge the message wasn't understood rather than
    silently repeating the exact same question, as if the assistant forgot
    the conversation (universal-sales-cycle-model.md section 7.3)."""
    intake = service_with({
        "msg-established": valid_intent(),
        "msg-gibberish": IntentResult(confidence=0.95, unintelligible=True),
    })

    first = intake.receive(message("msg-established", name=None, phone=None))
    second = intake.receive(message("msg-gibberish", case_id=first.case_id, name=None, phone=None))

    assert first.qualification.missing_fields == ("name", "phone")
    assert second.current_state is ProcessState.QUALIFYING
    assert not second.qualification.requires_human
    assert second.qualification.missing_fields == ("name", "phone")
    assert second.response is not None
    assert "service" not in second.response.message_text.casefold()
    assert second.response.message_text == (
        "Sorry, I didn't quite catch that — "
        "What name should we use for the request? What is the best phone number to reach you?"
    )


def test_unintelligible_input_escalates_after_clarification_attempts_exhausted() -> None:
    """MAX_CLARIFICATION_ATTEMPTS bounds the automated retry loop -- a
    customer whose messages are never interpretable must still reach a
    human eventually, mirroring MAX_REASSURANCE_ATTEMPTS."""
    from src.engine.qualification_service import QualificationService

    gibberish = IntentResult(confidence=0.95, unintelligible=True)
    intake = service_with({f"msg-{index}": gibberish for index in range(QualificationService.MAX_CLARIFICATION_ATTEMPTS + 1)})

    case_id = None
    results = []
    for index in range(QualificationService.MAX_CLARIFICATION_ATTEMPTS + 1):
        result = intake.receive(message(f"msg-{index}", case_id=case_id))
        case_id = result.case_id
        results.append(result)

    assert [result.current_state for result in results[:-1]] == [ProcessState.QUALIFYING] * QualificationService.MAX_CLARIFICATION_ATTEMPTS
    assert results[-1].current_state is ProcessState.NEEDS_HUMAN
    assert results[-1].qualification.requires_human
    qualification_event = next(
        event
        for event in intake.get_case(case_id).event_history
        if event.event_type is EventType.QUALIFICATION_EVALUATED
        and event.payload["recommended_next_state"] == "NEEDS_HUMAN"
    )
    assert qualification_event.payload["escalation_reason"] == "unintelligible"


def test_normal_request_after_gibberish_recovers_without_sticky_flag() -> None:
    intake = service_with({
        "msg-noise": IntentResult(confidence=0.1, unintelligible=True),
        "msg-clear": valid_intent(),
    })
    first = intake.receive(message("msg-noise"))

    second = intake.receive(message("msg-clear", case_id=first.case_id))

    assert first.current_state is ProcessState.QUALIFYING
    assert second.current_state is ProcessState.QUALIFIED
    intent_events = [
        event for event in intake.get_case(first.case_id).event_history
        if event.event_type is EventType.INTENT_EXTRACTED
    ]
    assert [event.payload["unintelligible"] for event in intent_events] == [True, False]


def test_emergency_intent_records_safe_escalation_reason_code() -> None:
    intake = service_with({
        "msg-emergency": valid_intent(
            urgency=Urgency.EMERGENCY,
            requires_human=True,
        )
    })

    result = intake.receive(message("msg-emergency"))

    assert result.current_state is ProcessState.NEEDS_HUMAN
    qualification_event = next(
        event
        for event in intake.get_case(result.case_id).event_history
        if event.event_type is EventType.QUALIFICATION_EVALUATED
    )
    assert qualification_event.payload["escalation_reason"] == "safety_emergency"


def test_duplicate_external_message_is_idempotent_without_new_case_or_events() -> None:
    intake = service_with({"msg-f": valid_intent()})
    first = intake.receive(message("msg-f"))
    case = intake.get_case(first.case_id)
    event_count = len(case.event_history)

    duplicate = intake.receive(message("msg-f", phone="+1 (312) 555-0100"))

    assert duplicate.duplicate
    assert duplicate.case_id == first.case_id
    assert len(intake.cases) == 1
    assert len(case.event_history) == event_count


def test_duplicate_id_with_different_content_is_rejected() -> None:
    intake = service_with({"collision": valid_intent()})
    original = message("collision")
    intake.receive(original)
    with pytest.raises(ValueError, match="reused with different"):
        intake.receive(replace(original, raw_text="Different payload"))


def test_service_specific_question_must_be_answered_before_qualification() -> None:
    dna = deepcopy(business_dna())
    dna["services"][0]["qualification_questions"] = [{
        "id": "property_type",
        "prompt": "Is this a residential or commercial property?",
        "required": True,
        "disqualifying_answers": [],
    }]
    intake = service_with({
        "msg-g": valid_intent(),
        "msg-g2": IntentResult(
            confidence=0.95,
            qualification_answers={"property_type": "residential"},
        ),
    }, dna)

    result = intake.receive(message("msg-g"))

    assert result.current_state is ProcessState.QUALIFYING
    assert result.qualification.unanswered_questions == (
        "Is this a residential or commercial property?",
    )
    assert result.response is not None
    assert result.response.message_text == "Is this a residential or commercial property?"

    answered = intake.receive(message("msg-g2", case_id=result.case_id))
    assert answered.current_state is ProcessState.QUALIFIED


def test_existing_lead_adds_information_and_same_case_progresses() -> None:
    intake = service_with({
        "msg-h1": valid_intent(),
        "msg-h2": IntentResult(confidence=0.95),
    })
    first = intake.receive(message("msg-h1", phone=None))

    second = intake.receive(message("msg-h2", phone="+1 312 555 0100", case_id=first.case_id))

    assert first.current_state is ProcessState.QUALIFYING
    assert second.current_state is ProcessState.QUALIFIED
    assert not second.case_created
    assert second.case_id == first.case_id
    assert second.lead_id == first.lead_id
    assert len(intake.cases) == 1
    assert intake.get_case(first.case_id).lead.phone == "+13125550100"


def test_existing_lead_is_found_by_normalized_phone() -> None:
    intake = service_with({
        "msg-i1": valid_intent(customer_location=None),
        "msg-i2": valid_intent(),
    })
    first = intake.receive(message("msg-i1", phone="+1 (312) 555-0100"))
    second = intake.receive(message("msg-i2", phone="+1 312 555 0100"))
    assert second.case_id == first.case_id
    assert len(intake.cases) == 1


def test_input_scope_and_timestamp_are_validated() -> None:
    intake = service_with({})
    with pytest.raises(ValueError, match="timezone-aware"):
        IncomingMessage("acme-home-services", "sms", "x", "hello", datetime.now())
    with pytest.raises(ValueError, match="channel is not enabled"):
        intake.receive(IncomingMessage("acme-home-services", "fax", "x", "hello", NOW))
    with pytest.raises(ValueError, match="does not match"):
        intake.receive(IncomingMessage("other-business", "sms", "x", "hello", NOW))
    with pytest.raises(ValueError, match="email is not valid"):
        intake.receive(message("bad-email", email="not-an-email"))
    with pytest.raises(ValueError, match="between 7 and 15"):
        intake.receive(message("bad-phone", phone="123"))


def test_booking_policy_is_reflected_in_qualified_result() -> None:
    dna = deepcopy(business_dna())
    dna["booking"]["enabled"] = False
    result = service_with({"no-booking": valid_intent()}, dna).receive(message("no-booking"))
    assert result.qualification.qualified
    assert not result.qualification.booking_allowed


def test_semantically_unsafe_business_dna_is_rejected_at_startup() -> None:
    missing_prompt = deepcopy(business_dna())
    del missing_prompt["customer_information"]["field_questions"]["phone"]
    with pytest.raises(ValueError, match="no configured questions"):
        service_with({}, missing_prompt)

    ambiguous = deepcopy(business_dna())
    second_service = deepcopy(ambiguous["services"][0])
    second_service["id"] = "second-service"
    ambiguous["services"].append(second_service)
    with pytest.raises(ValueError, match="ambiguous"):
        service_with({}, ambiguous)


class FailingExtractor:
    def extract(self, message: IncomingMessage, business_dna: dict) -> IntentResult:
        raise RuntimeError("provider failed")


def test_extraction_failure_does_not_leave_an_orphan_case() -> None:
    intake = LeadIntakeService(business_dna(), FailingExtractor(), DeterministicQuestionGenerator())
    with pytest.raises(RuntimeError, match="provider failed"):
        intake.receive(message("failed"))
    assert intake.cases == ()

def test_a_corrected_fact_replaces_the_earlier_one() -> None:
    """The newest thing the customer said must win.

    Until 2026-08-30 the FIRST value won forever, and any later different value
    additionally set a conflict flag, which forces requires_human. So a
    self-correction was impossible to express: the engine kept the old value
    AND fetched a person because the two differed.

    Found on production: told "that ZIP is outside our service area, send
    another one if you have one nearby", the customer answered "sorry, typo,
    it's actually 90210" -- a ZIP the business does serve -- and was told again
    that their address was outside the area. We invite the correction and then
    refuse it.

    Both ZIPs here are inside the service area, and both turns deliberately
    leave name and phone missing so the case stays QUALIFYING: this test is
    about the merge. The real out-of-area -> correction -> cycle-continues path
    crosses LOST, which this layer cannot re-enter (see ACTIVE_STATES), so it
    belongs in a conversation-level test where reactivation lives.
    """
    intake = service_with({
        "first": valid_intent(customer_location="60601"),
        "corrected": valid_intent(customer_location="60602"),
    })

    first = intake.receive(message("first", name=None, phone=None))
    intake.receive(message("corrected", name=None, phone=None, case_id=first.case_id))

    assert first.current_state is ProcessState.QUALIFYING
    assert intake.get_case(first.case_id).metadata["customer_location"] == "60602"


def test_a_correction_alone_does_not_escalate() -> None:
    """Changing your own mind is not a reason to fetch a person.

    Location and preferred time are the customer restating their own request.
    Identity is different and still escalates -- the phone/email/name checks in
    _merge_intent are untouched, because a changed phone number can mean a
    different person on the same conversation.
    """
    intake = service_with({
        "first": valid_intent(customer_location="60601", preferred_time="Monday"),
        "second": valid_intent(customer_location="60602", preferred_time="Tuesday"),
    })

    first = intake.receive(message("first", name=None, phone=None))
    second = intake.receive(message("second", name=None, phone=None, case_id=first.case_id))

    assert not second.qualification.requires_human


def test_silence_still_preserves_a_known_fact() -> None:
    """The reason the old behaviour existed at all -- keep it.

    A message carrying no location must not wipe the location already on the
    case, otherwise a bare "yes" would restart qualification.
    """
    intake = service_with({
        "with-zip": valid_intent(customer_location="60601"),
        "no-zip": valid_intent(customer_location=None),
    })

    first = intake.receive(message("with-zip", name=None, phone=None))
    intake.receive(message("no-zip", name=None, phone=None, case_id=first.case_id))

    assert intake.get_case(first.case_id).metadata["customer_location"] == "60601"


def test_unsupported_service_request_clears_the_stale_established_service() -> None:
    """An unsupported-service mention is not silence.

    Found live while QA-testing the "unsupported service" scenario across
    five business types (2026-08-31): a case with an already-established
    service (e.g. diagnostic-visit) that later asked about something
    unsupported (e.g. a roof replacement) kept "diagnostic-visit" as
    service_requested in QUALIFICATION_EVALUATED and case.metadata, even
    though the customer's current message was about something else
    entirely and had just been declined for it. corrected_fact() cannot
    tell "the customer said nothing about service this turn" apart from
    "the customer asked for something we don't offer" -- both leave
    current.service_requested None -- so it silently preserved the old
    value. The LOST decision itself was already correct (driven by
    unsupported_service_name, not service_requested), but the persisted
    audit trail was misleading.
    """
    intake = service_with({
        "established": valid_intent(service_requested="diagnostic-visit"),
        "unsupported": valid_intent(service_requested=None, unsupported_service_name="a roof replacement"),
    })

    first = intake.receive(message("established", name=None, phone=None))
    second = intake.receive(message("unsupported", name=None, phone=None, case_id=first.case_id))

    assert second.current_state is ProcessState.LOST
    case = intake.get_case(first.case_id)
    assert case.metadata["unsupported_service_name"] == "a roof replacement"
    # Not re-stamped with the stale prior service -- case.metadata simply
    # keeps whatever it already had (still "diagnostic-visit" from the
    # first turn, untouched) rather than looking freshly re-confirmed.
    assert case.metadata["service_requested"] == "diagnostic-visit"
    # The actual fix, observable here: the merged IntentResult for THIS
    # turn no longer carries the stale "diagnostic-visit" forward into the
    # lead's own attributes (case.update_lead runs every turn, unlike
    # case.metadata which is only ever additively set) -- before the fix
    # this stayed "diagnostic-visit" even on the turn that asked about a
    # roof replacement instead.
    assert case.lead.attributes["service_requested"] is None


def test_a_vague_first_message_gets_a_question_not_a_handoff() -> None:
    """The behaviour the whole product rests on.

    Found live on 2026-09-01: a first message of "Hi! what do you want?" was
    answered with "one of our team members is gonna take a look at your
    request and get back to you soon" and the case went to NEEDS_HUMAN on
    turn one. Low confidence escalated on the spot without asking anything,
    while only intent.unintelligible got the clarification loop -- and
    prompts.py deliberately keeps those two flags apart. So the most common
    real opening message ended the automated cycle immediately, which is
    intake, not "from enquiry to deal".
    """
    intake = service_with({"vague": valid_intent(confidence=0.2, service_requested=None)})

    result = intake.receive(message("vague", name=None, phone=None))

    assert result.current_state is ProcessState.QUALIFYING
    assert not result.qualification.requires_human
    assert result.response is not None


def test_repeated_low_confidence_still_reaches_a_person() -> None:
    """The cap is what keeps the loop honest.

    A customer whose messages never become interpretable must not be kept
    talking to the engine forever -- after MAX_CLARIFICATION_ATTEMPTS the
    case escalates exactly as it did before.
    """
    intake = service_with({
        "one": valid_intent(confidence=0.2, service_requested=None),
        "two": valid_intent(confidence=0.2, service_requested=None),
        "three": valid_intent(confidence=0.2, service_requested=None),
        "four": valid_intent(confidence=0.2, service_requested=None),
    })

    first = intake.receive(message("one", name=None, phone=None))
    for external_id in ("two", "three", "four"):
        last = intake.receive(message(external_id, name=None, phone=None, case_id=first.case_id))

    assert last.current_state is ProcessState.NEEDS_HUMAN


def test_a_complete_case_read_with_low_confidence_still_goes_to_a_person() -> None:
    """The clarification loop must not buy a booking on a shaky reading.

    Low confidence means the service or answers extracted this turn may be
    wrong. While the case is incomplete the engine asks another question;
    once everything required is present it still hands to a person, exactly
    as it did before low confidence joined the loop.
    """
    intake = service_with({"complete": valid_intent(confidence=0.2)})

    result = intake.receive(message("complete"))

    assert result.current_state is ProcessState.NEEDS_HUMAN

