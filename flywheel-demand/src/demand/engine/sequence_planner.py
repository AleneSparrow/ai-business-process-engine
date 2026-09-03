"""Permission-based welcome sequence. Not cold outreach; opt-in is required to send."""

from __future__ import annotations

from typing import Any, Mapping

from src.demand.domain.consent import ConsentChannel
from src.demand.domain.models import SequenceStep
from src.demand.engine.consent_gate import email_footer, sms_footer


_WELCOME = (
    (1, 0, "deliver_promise", "Confirm the signup and deliver the promised explanation of the job."),
    (2, 48, "brand_fit", "State who this is for, using the approved positioning statement."),
    (3, 96, "value", "Restate the job and the cost of guessing, without a pitch."),
    (4, 168, "proof", "Use only owner-substantiated proof claims. Skip if none exist."),
    (5, 240, "soft_offer", "Invite an inquiry. Do not invent urgency or discounts."),
)


def compile_welcome_sequence(marketing_dna: Mapping[str, Any]) -> tuple[SequenceStep, ...]:
    if not marketing_dna.get("motions", {}).get("loyalty"):
        return ()
    channel = str((marketing_dna.get("sequences") or {}).get("welcome", {}).get("channel") or "email")
    include_proof = bool((marketing_dna.get("sequences") or {}).get("welcome", {}).get("include_proof_step"))
    proof_ids = tuple(str(item) for item in marketing_dna.get("proof_claim_ids") or ())
    catalog_ids = tuple(str(item) for item in marketing_dna.get("approved_claim_ids") or () if not str(item).startswith("owner-"))
    consent = ConsentChannel.SMS if channel == "sms" else ConsentChannel.EMAIL

    steps: list[SequenceStep] = []
    index = 0
    for _, offset, purpose, summary in _WELCOME:
        if purpose == "proof" and not include_proof:
            continue
        index += 1
        claim_ids = proof_ids if purpose == "proof" else catalog_ids
        cta = "inquire" if purpose == "soft_offer" else "none"
        steps.append(SequenceStep(
            index=index,
            offset_hours=offset,
            purpose=purpose,
            channel=channel,
            summary=summary,
            allowed_claim_ids=claim_ids,
            cta=cta,
            requires_consent=consent,
        ))
    return tuple(steps)


def render_step(step: SequenceStep, marketing_dna: Mapping[str, Any], *, first_name: str | None = None) -> str:
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    statement = str((marketing_dna.get("positioning") or {}).get("statement") or "").strip()
    claims = {
        str(item["id"]): str(item["text"])
        for item in (marketing_dna.get("positioning") or {}).get("claims") or ()
        if item.get("status") == "approved"
    }
    allowed = " ".join(claims[claim_id] for claim_id in step.allowed_claim_ids if claim_id in claims)
    job = str(((marketing_dna.get("market") or {}).get("jobs") or ["this job"])[0])

    if step.purpose == "deliver_promise":
        body = (
            f"{greeting}\n\nThanks for signing up. Here is what {job.casefold()} involves "
            f"and how to tell whether you need help. {allowed}"
        )
    elif step.purpose == "brand_fit":
        body = f"{greeting}\n\n{statement} {allowed}"
    elif step.purpose == "value":
        body = (
            f"{greeting}\n\nMost people lose time when they guess the next step for "
            f"{job.casefold()}. {allowed}"
        )
    elif step.purpose == "proof":
        body = f"{greeting}\n\n{allowed or 'We only share results we can document.'}"
    else:
        body = (
            f"{greeting}\n\nIf you want help with {job.casefold()}, reply and tell us what you need. "
            f"That message becomes an inbound request — we do not keep pitching after that. {allowed}"
        )

    if step.channel == "sms":
        return f"{body}{sms_footer()}"
    return f"{body}{email_footer(marketing_dna)}"
