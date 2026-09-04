"""Approved first-turn sales presentation.

The engine does not invent a pitch. It sends `sales.opening_pitch` when the
owner wrote one, otherwise a sentence composed only from the business name,
description, and service names already in Business DNA. AI may rephrase this
text; it may not add offers, prices, or commitments.
"""

from typing import Mapping


def compose_opening_pitch(
    business_name: str,
    description: str = "",
    service_names: tuple[str, ...] = (),
) -> str:
    name = business_name.strip() or "us"
    about = description.strip().rstrip(".")
    offer = _join_names(service_names)
    who = f"this is {name}" if name != "us" else "thanks for reaching out"
    about_sentence = f" {about}." if about else ""
    offer_sentence = f" We can help with {offer}." if offer else ""
    return (
        f"Hi — {who}.{about_sentence}{offer_sentence} "
        "Tell me what you're trying to get done and I'll walk you through the next step."
    )


def opening_pitch_from_dna(business_dna: Mapping[str, object]) -> str:
    sales = business_dna.get("sales")
    if isinstance(sales, Mapping):
        configured = sales.get("opening_pitch")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
    business = business_dna.get("business")
    business_map = business if isinstance(business, Mapping) else {}
    name = business_map.get("name") if isinstance(business_map.get("name"), str) else ""
    description = (
        business_map.get("description")
        if isinstance(business_map.get("description"), str)
        else ""
    )
    return compose_opening_pitch(str(name or ""), str(description or ""), _service_names(business_dna))


def _service_names(business_dna: Mapping[str, object]) -> tuple[str, ...]:
    services = business_dna.get("services")
    if not isinstance(services, list):
        return ()
    names: list[str] = []
    for service in services:
        if not isinstance(service, Mapping):
            continue
        name = service.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return tuple(names)


def _join_names(names: tuple[str, ...]) -> str:
    cleaned = tuple(name.strip() for name in names if name.strip())
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"
