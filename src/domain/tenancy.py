"""Tenant and versioned Business DNA domain records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text


@dataclass(frozen=True, slots=True)
class Business:
    business_id: str
    name: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.business_id, "business_id")
        _require_text(self.name, "name")
        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class BusinessDNAVersion:
    business_id: str
    version: int
    configuration: Mapping[str, Any]
    created_at: datetime
    active: bool

    def __post_init__(self) -> None:
        _require_text(self.business_id, "business_id")
        if self.version < 1:
            raise ValueError("Business DNA version must be positive")
        _require_aware(self.created_at, "created_at")
        object.__setattr__(self, "configuration", _freeze(self.configuration))
