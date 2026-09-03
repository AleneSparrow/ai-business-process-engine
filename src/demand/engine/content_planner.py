"""Deterministic content briefs from Marketing DNA. AI may later fill wording only."""

from __future__ import annotations

from typing import Any, Mapping

from src.demand.domain.models import ContentBrief


_STAGE_COPY = {
    "aware": "Explain the job and the cost of guessing. Do not pitch. Do not invent proof.",
    "engaged": "Help the reader compare doing it themselves, hiring staff, or working with this business. Use only approved claims.",
    "intent": "Say what happens after they reach out. The next step is an inquiry — not a sale.",
}


def compile_content_plan(marketing_dna: Mapping[str, Any]) -> tuple[ContentBrief, ...]:
    if not marketing_dna.get("motions", {}).get("attract"):
        return ()
    positioning = marketing_dna.get("positioning") or {}
    statement = str(positioning.get("statement") or "").strip()
    briefs: list[ContentBrief] = []
    for pillar in marketing_dna.get("content_plan", {}).get("pillars") or ():
        stage = str(pillar["stage"])
        job = str(pillar["job"])
        instruction = _STAGE_COPY.get(stage, _STAGE_COPY["aware"])
        summary = f"{instruction} Job: {job}. Positioning: {statement}"
        briefs.append(ContentBrief(
            brief_id=str(pillar["id"]),
            stage=stage,
            format=str(pillar["format"]),
            job=job,
            summary=summary,
            allowed_claim_ids=tuple(str(item) for item in pillar.get("allowed_claim_ids") or ()),
            cta=str(pillar.get("cta") or "none"),
            channel="web",
        ))
    return tuple(briefs)


def render_article(brief: ContentBrief, marketing_dna: Mapping[str, Any]) -> str:
    """Fill a brief with DNA-only sentences. No model, no new claims."""

    name = _business_name(marketing_dna)
    claims = {
        str(item["id"]): str(item["text"])
        for item in (marketing_dna.get("positioning") or {}).get("claims") or ()
        if item.get("status") == "approved"
    }
    allowed = [claims[claim_id] for claim_id in brief.allowed_claim_ids if claim_id in claims]
    claim_block = " ".join(allowed)
    if brief.format == "explainer":
        return (
            f"If you need {brief.job.casefold()}, the useful first step is to understand the job "
            f"before you commit. {claim_block} This article does not ask you to buy anything."
        )
    if brief.format == "comparison":
        alternatives = list((marketing_dna.get("market") or {}).get("alternatives") or ())
        alt = alternatives[0] if alternatives else "handle the job themselves"
        return (
            f"People who need {brief.job.casefold()} usually {alt}, or they talk to a provider. "
            f"{claim_block} {name} publishes this so you can decide fit before you reach out."
        )
    return (
        f"When you are ready, reach out and say what you need. {claim_block} "
        f"After you inquire, the conversation is handled as an inbound request — not a cold pitch."
    )


def _business_name(marketing_dna: Mapping[str, Any]) -> str:
    statement = str((marketing_dna.get("positioning") or {}).get("statement") or "")
    if " is a " in statement:
        left = statement.split(" is a ", 1)[0]
        if ", " in left:
            return left.rsplit(", ", 1)[-1].strip()
    return "This business"
