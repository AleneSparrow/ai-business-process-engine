"""Local value helpers. Demand does not import the Flywheel process engine."""

from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(freeze(item) for item in value)
    return value
