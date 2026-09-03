"""Compile Marketing DNA from Business DNA plus optional owner answers.

Zero-config is a requirement: a tenant that already has Business DNA can
obtain a valid Marketing DNA without a strategist. Extra onboarding fields
only add owner-substantiated claims and a mailing address.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.demand.domain.primitives import require_text

from .claims import Claim, ClaimStatus, SubstantiationKind

SCHEMA_VERSION = "1.0"

DEFAULT_ALTERNATIVES = (
    "handle the job themselves",
    "hire extra staff to chase every inquiry by hand",
    "use a generic tool that is not set up for this business",
)

DEFAULT_PAINS = (
    "not knowing whether a provider is a fit",
    "wasting time on the wrong next step",
    "starting a conversation without knowing what happens next",
)

DEFAULT_GAINS = (
    "a clear next step",
    "a provider who already explains what they do",
    "reaching out only when ready",
)

_SUPERLATIVE_TOKENS = (
    "best",
    "#1",
    "number one",
    "guaranteed",
    "guarantee",
    "100%",
    "risk-free",
    "risk free",
)


@dataclass(frozen=True, slots=True)
class ProofClaimInput:
    text: str
    evidence: str

    def __post_init__(self) -> None:
        require_text(self.text, "text")
        require_text(self.evidence, "evidence")


@dataclass(frozen=True, slots=True)
class MarketingOnboardingInput:
    """Optional extras on top of Business DNA. Every field has a safe default."""

    jobs: tuple[str, ...] = ()
    competitive_alternatives: tuple[str, ...] = ()
    proof_claims: tuple[ProofClaimInput, ...] = ()
    physical_postal_address: str | None = None
    attract_enabled: bool = True
    loyalty_enabled: bool = True
    primary_segment_label: str | None = None

    def __post_init__(self) -> None:
        if not self.attract_enabled and not self.loyalty_enabled:
            raise ValueError("at least one motion (attract or loyalty) must be enabled")
        if self.physical_postal_address is not None:
            require_text(self.physical_postal_address, "physical_postal_address")
        if self.primary_segment_label is not None:
            require_text(self.primary_segment_label, "primary_segment_label")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _service_names(business_dna: Mapping[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for service in business_dna.get("services") or ():
        name = _text(service.get("name"))
        if name:
            names.append(name)
    if not names:
        raise ValueError("Business DNA must include at least one named service")
    return tuple(names)


def _service_jobs(business_dna: Mapping[str, Any], extra: tuple[str, ...]) -> tuple[str, ...]:
    jobs: list[str] = []
    seen: set[str] = set()
    for raw in extra + _service_names(business_dna):
        job = raw.strip()
        key = job.casefold()
        if job and key not in seen:
            seen.add(key)
            jobs.append(job)
    return tuple(jobs)


def _geography(business_dna: Mapping[str, Any]) -> str:
    areas = list(business_dna.get("service_areas") or ())
    if not areas:
        return "the United States"
    first = areas[0]
    area_type = _text(first.get("type")).casefold()
    values = [str(item).strip() for item in (first.get("values") or ()) if str(item).strip()]
    if area_type == "remote" or not values:
        return "the United States"
    if area_type == "postal_codes":
        if len(values) == 1:
            return f"ZIP {values[0]}"
        return f"ZIPs {', '.join(values[:3])}" + (" and nearby" if len(values) > 3 else "")
    return values[0]


def _slug(value: str, fallback: str = "item") -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or fallback


def _claim_from_dna(claim_id: str, text: str) -> dict[str, str]:
    return {
        "id": claim_id,
        "text": text,
        "substantiation": SubstantiationKind.BUSINESS_DNA.value,
        "status": ClaimStatus.APPROVED.value,
        "evidence": "Copied from Business DNA; not an advertising superlative.",
    }


def _owner_claim(index: int, proof: ProofClaimInput) -> dict[str, str]:
    blocked = any(token in proof.text.casefold() for token in _SUPERLATIVE_TOKENS) and not proof.evidence.strip()
    status = ClaimStatus.BLOCKED.value if blocked else ClaimStatus.APPROVED.value
    return {
        "id": f"owner-{index}",
        "text": proof.text.strip(),
        "substantiation": SubstantiationKind.OWNER_SUPPLIED.value,
        "status": status,
        "evidence": proof.evidence.strip(),
    }


def claims_from_dna(marketing_dna: Mapping[str, Any]) -> tuple[Claim, ...]:
    built: list[Claim] = []
    for raw in marketing_dna.get("positioning", {}).get("claims") or ():
        built.append(Claim(
            claim_id=str(raw["id"]),
            text=str(raw["text"]),
            substantiation=SubstantiationKind(raw["substantiation"]),
            status=ClaimStatus(raw["status"]),
            evidence=str(raw.get("evidence") or ""),
        ))
    return tuple(built)


def build_marketing_dna(
    business_dna: Mapping[str, Any],
    onboarding: MarketingOnboardingInput | None = None,
) -> dict[str, Any]:
    """Deterministically compile Marketing DNA. No model is called."""

    extras = onboarding or MarketingOnboardingInput()
    business = business_dna.get("business") or {}
    business_id = _text(business.get("id"))
    name = _text(business.get("name"))
    industry = _text(business.get("industry")) or "services"
    if not business_id:
        raise ValueError("Business DNA is missing business.id")
    if not name:
        raise ValueError("Business DNA is missing business.name")

    jobs = _service_jobs(business_dna, extras.jobs)
    alternatives = extras.competitive_alternatives or DEFAULT_ALTERNATIVES
    geography = _geography(business_dna)
    primary_job = jobs[0]
    segment_label = extras.primary_segment_label or f"People who need {primary_job.casefold()}"
    service_list = ", ".join(jobs)
    communication = business_dna.get("communication") or {}
    tone = _text(communication.get("tone")) or "friendly, concise, and professional"
    language = _text(communication.get("language")) or "English"

    statement = (
        f"For {segment_label.casefold()} in {geography}, {name} is a {industry.replace('_', ' ')} "
        f"business that offers {service_list}, unlike {alternatives[0]}."
    )

    claims = [
        _claim_from_dna("offers-catalog", f"{name} offers {service_list}."),
        _claim_from_dna("serves-geography", f"{name} serves {geography}."),
    ]
    for index, proof in enumerate(extras.proof_claims, start=1):
        claims.append(_owner_claim(index, proof))

    approved_ids = [item["id"] for item in claims if item["status"] == ClaimStatus.APPROVED.value]
    proof_ids = [item["id"] for item in claims if item["id"].startswith("owner-") and item["status"] == ClaimStatus.APPROVED.value]

    return {
        "schema_version": SCHEMA_VERSION,
        "business_id": business_id,
        "market": {
            "geography": geography,
            "category": industry.replace("_", " "),
            "jobs": list(jobs),
            "pains": list(DEFAULT_PAINS),
            "gains": list(DEFAULT_GAINS),
            "alternatives": list(alternatives),
        },
        "segments": [
            {
                "id": "primary",
                "label": segment_label,
                "jobs": list(jobs),
                "pains": list(DEFAULT_PAINS),
            }
        ],
        "targeting": {
            "primary_segment_id": "primary",
            "strategy": "concentrated",
        },
        "positioning": {
            "competitive_alternatives": list(alternatives),
            "unique_attributes": list(jobs),
            "value_themes": [f"A clear path to get {primary_job.casefold()} done"],
            "best_fit_customers": segment_label,
            "market_category": industry.replace("_", " "),
            "statement": statement,
            "claims": claims,
        },
        "motions": {
            "attract": extras.attract_enabled,
            "loyalty": extras.loyalty_enabled,
        },
        "content_plan": {
            "pillars": [
                {
                    "id": "problem",
                    "stage": "aware",
                    "format": "explainer",
                    "job": primary_job,
                    "cta": "subscribe" if extras.loyalty_enabled else "inquire",
                    "allowed_claim_ids": approved_ids[:2],
                },
                {
                    "id": "fit",
                    "stage": "engaged",
                    "format": "comparison",
                    "job": primary_job,
                    "cta": "inquire",
                    "allowed_claim_ids": approved_ids[:2],
                },
                {
                    "id": "next-step",
                    "stage": "intent",
                    "format": "next_step",
                    "job": primary_job,
                    "cta": "inquire",
                    "allowed_claim_ids": approved_ids[:2],
                },
            ]
        },
        "sequences": {
            "welcome": {
                "channel": "email",
                "include_proof_step": bool(proof_ids),
            }
        },
        "scoring": {
            "aware_min": 5,
            "engaged_min": 20,
            "intent_min": 45,
        },
        "communication": {
            "language": language,
            "tone": tone,
        },
        "compliance": {
            "ai_disclosure_required": True,
            "can_spam": True,
            "tcpa_sms": True,
            "physical_postal_address": extras.physical_postal_address,
            "unsubscribe_required": True,
            "opt_in_required_for_loyalty": True,
        },
        "handoff": {
            "target": "business_process_engine",
            "entry_state": "NEW_LEAD",
            "source": "flywheel_demand",
        },
        "approved_claim_ids": approved_ids,
        "proof_claim_ids": proof_ids,
    }
