"""Conversation domain values for tenant-scoped, multi-turn customer chat."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .models import _freeze, _require_aware, _require_text


class ConversationStatus(StrEnum):
    AI_ACTIVE = "ai_active"
    HUMAN_TAKEOVER_REQUESTED = "human_takeover_requested"
    HUMAN_TAKEOVER_ACTIVE = "human_takeover_active"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageRole(StrEnum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"
    HUMAN = "human"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class ConversationContextMessage:
    role: MessageRole
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, MessageRole):
            raise TypeError("context message role must be a MessageRole")
        _require_text(self.text, "context message text")
        if len(self.text) > 2_000:
            raise ValueError("context message text must not exceed 2000 characters")


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Bounded, derived context supplied to intent extraction only."""

    recent_messages: tuple[ConversationContextMessage, ...] = ()
    known_facts: Mapping[str, Any] = field(default_factory=dict)
    unresolved_items: tuple[str, ...] = ()
    current_state: str | None = None

    def __post_init__(self) -> None:
        if len(self.recent_messages) > 8:
            raise ValueError("conversation context must contain at most 8 recent messages")
        if len(self.unresolved_items) > 50:
            raise ValueError("conversation context must contain at most 50 unresolved items")
        object.__setattr__(self, "recent_messages", tuple(self.recent_messages))
        object.__setattr__(self, "unresolved_items", tuple(self.unresolved_items))
        object.__setattr__(self, "known_facts", _freeze(self.known_facts))


@dataclass(slots=True)
class Conversation:
    conversation_id: str
    business_id: str
    token_hash: str
    channel: str
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    token_expires_at: datetime
    lead_id: str | None = None
    case_id: str | None = None
    external_session_id: str | None = None
    token_revoked_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def __post_init__(self) -> None:
        for value, name in (
            (self.conversation_id, "conversation_id"),
            (self.business_id, "business_id"),
            (self.token_hash, "token_hash"),
            (self.channel, "channel"),
        ):
            _require_text(value, name)
        if not isinstance(self.status, ConversationStatus):
            raise TypeError("status must be a ConversationStatus")
        if not re.fullmatch(r"[0-9a-f]{64}", self.token_hash):
            raise ValueError("token_hash must be a lowercase SHA-256 digest")
        limits = {
            "conversation_id": (self.conversation_id, 128),
            "business_id": (self.business_id, 128),
            "channel": (self.channel, 64),
            "lead_id": (self.lead_id, 128),
            "case_id": (self.case_id, 128),
            "external_session_id": (self.external_session_id, 255),
        }
        for name, (value, maximum) in limits.items():
            if value is not None and len(value) > maximum:
                raise ValueError(f"{name} must not exceed {maximum} characters")
        for value, name in (
            (self.lead_id, "lead_id"),
            (self.case_id, "case_id"),
            (self.external_session_id, "external_session_id"),
        ):
            if value is not None:
                _require_text(value, name)
        for value, name in (
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
            (self.last_activity_at, "last_activity_at"),
            (self.token_expires_at, "token_expires_at"),
        ):
            _require_aware(value, name)
        if self.token_revoked_at is not None:
            _require_aware(self.token_revoked_at, "token_revoked_at")
            if self.token_revoked_at < self.created_at:
                raise ValueError("token_revoked_at must not precede created_at")
        if self.updated_at < self.created_at or self.last_activity_at < self.created_at:
            raise ValueError("conversation timestamps must not precede created_at")
        if self.token_expires_at <= self.created_at:
            raise ValueError("conversation token must expire after creation")
        if self.version < 0:
            raise ValueError("conversation version must not be negative")
        self.metadata = dict(self.metadata)

    def link_case(self, lead_id: str, case_id: str) -> None:
        _require_text(lead_id, "lead_id")
        _require_text(case_id, "case_id")
        if self.lead_id not in (None, lead_id) or self.case_id not in (None, case_id):
            raise ValueError("conversation cannot be relinked to another lead or case")
        self.lead_id = lead_id
        self.case_id = case_id

    def touch(self, occurred_at: datetime) -> None:
        _require_aware(occurred_at, "occurred_at")
        if occurred_at > self.last_activity_at:
            self.last_activity_at = occurred_at
        if occurred_at > self.updated_at:
            self.updated_at = occurred_at

    def set_status(self, status: ConversationStatus, occurred_at: datetime) -> None:
        allowed = {
            ConversationStatus.AI_ACTIVE: {
                ConversationStatus.HUMAN_TAKEOVER_REQUESTED,
                ConversationStatus.CLOSED,
            },
            ConversationStatus.HUMAN_TAKEOVER_REQUESTED: {
                ConversationStatus.HUMAN_TAKEOVER_ACTIVE,
                ConversationStatus.CLOSED,
            },
            ConversationStatus.HUMAN_TAKEOVER_ACTIVE: {ConversationStatus.CLOSED},
            ConversationStatus.CLOSED: set(),
        }
        if status is self.status:
            self.touch(occurred_at)
            return
        if status not in allowed[self.status]:
            raise ValueError(f"invalid conversation status transition: {self.status} -> {status}")
        self.status = status
        self.touch(occurred_at)

    def mark_persisted(self, version: int) -> None:
        if version <= self.version:
            raise ValueError("persisted version must advance")
        self.version = version


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    message_id: str
    business_id: str
    conversation_id: str
    sequence_number: int
    direction: MessageDirection
    role: MessageRole
    text: str
    created_at: datetime
    external_message_id: str | None = None
    content_fingerprint: str | None = None
    correlation_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.message_id, "message_id"),
            (self.business_id, "business_id"),
            (self.conversation_id, "conversation_id"),
            (self.text, "text"),
        ):
            _require_text(value, name)
        if not isinstance(self.direction, MessageDirection):
            raise TypeError("direction must be a MessageDirection")
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be a MessageRole")
        if (
            self.direction is MessageDirection.INBOUND
            and self.role is not MessageRole.CUSTOMER
        ) or (
            self.direction is MessageDirection.OUTBOUND
            and self.role is MessageRole.CUSTOMER
        ):
            raise ValueError("message direction and role are inconsistent")
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        _require_aware(self.created_at, "created_at")
        for value, name in (
            (self.external_message_id, "external_message_id"),
            (self.content_fingerprint, "content_fingerprint"),
            (self.correlation_id, "correlation_id"),
        ):
            if value is not None:
                _require_text(value, name)
        if self.external_message_id is not None and len(self.external_message_id) > 255:
            raise ValueError("external_message_id must not exceed 255 characters")
        for name, value in (
            ("message_id", self.message_id),
            ("business_id", self.business_id),
            ("conversation_id", self.conversation_id),
            ("correlation_id", self.correlation_id),
        ):
            if value is not None and len(value) > 128:
                raise ValueError(f"{name} must not exceed 128 characters")
        if (self.external_message_id is None) != (self.content_fingerprint is None):
            raise ValueError("external_message_id and content_fingerprint must be supplied together")
        if self.content_fingerprint is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.content_fingerprint
        ):
            raise ValueError("content_fingerprint must be a lowercase SHA-256 digest")
        object.__setattr__(self, "metadata", _freeze(self.metadata))
