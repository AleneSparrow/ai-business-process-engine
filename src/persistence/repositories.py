"""Persistence protocols; domain and engine code contain no SQL."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Protocol

from src.domain.models import Lead, ProcessCase, ProcessEvent
from src.domain.conversations import Conversation, ConversationMessage
from src.domain.tenancy import Business, BusinessDNAVersion


class ClaimStatus(StrEnum):
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    business_id: str
    channel: str
    external_message_id: str
    fingerprint: str
    case_id: str | None
    result: Mapping[str, Any] | None
    created_at: datetime


class BusinessRepository(Protocol):
    def add(self, business: Business) -> None: ...
    def get(self, business_id: str) -> Business | None: ...


class BusinessDNARepository(Protocol):
    def add_version(self, business_id: str, configuration: Mapping[str, Any]) -> BusinessDNAVersion: ...
    def get_active(self, business_id: str) -> BusinessDNAVersion | None: ...
    def list_versions(self, business_id: str) -> tuple[BusinessDNAVersion, ...]: ...


class LeadRepository(Protocol):
    def lock_identity(
        self,
        business_id: str,
        identity_type: str,
        normalized_value: str,
    ) -> None: ...
    def add(self, business_id: str, lead: Lead, created_at: datetime) -> None: ...
    def save(self, business_id: str, lead: Lead, updated_at: datetime) -> None: ...
    def get(self, business_id: str, lead_id: str) -> Lead | None: ...
    def find_by_identity(
        self,
        business_id: str,
        normalized_phone: str | None,
        normalized_email: str | None,
    ) -> Lead | None: ...


class ProcessCaseRepository(Protocol):
    def add(self, case: ProcessCase) -> None: ...
    def get(self, business_id: str, case_id: str) -> ProcessCase | None: ...
    def find_active_for_lead(self, business_id: str, lead_id: str) -> ProcessCase | None: ...
    def save(self, case: ProcessCase, expected_version: int) -> None: ...


class ProcessEventRepository(Protocol):
    def add(self, business_id: str, case_id: str, event: ProcessEvent) -> None: ...
    def add_many(self, business_id: str, case_id: str, events: tuple[ProcessEvent, ...]) -> None: ...
    def list_for_case(self, business_id: str, case_id: str) -> tuple[ProcessEvent, ...]: ...


class IdempotencyRepository(Protocol):
    def claim(
        self,
        business_id: str,
        channel: str,
        external_message_id: str,
        fingerprint: str,
    ) -> tuple[ClaimStatus, IdempotencyRecord]: ...
    def complete(
        self,
        business_id: str,
        channel: str,
        external_message_id: str,
        case_id: str,
        result: Mapping[str, Any],
    ) -> None: ...
    def get(self, business_id: str, channel: str, external_message_id: str) -> IdempotencyRecord | None: ...


class ConversationRepository(Protocol):
    def lock_token_identity(self, business_id: str, token_hash: str) -> None: ...
    def add(self, conversation: Conversation) -> None: ...
    def get(self, business_id: str, conversation_id: str, *, for_update: bool = False) -> Conversation | None: ...
    def get_by_token_hash(self, business_id: str, token_hash: str, *, for_update: bool = False) -> Conversation | None: ...
    def save(self, conversation: Conversation, expected_version: int) -> None: ...


class ConversationMessageRepository(Protocol):
    def add(self, message: ConversationMessage) -> None: ...
    def get_by_external_id(
        self, business_id: str, conversation_id: str, external_message_id: str
    ) -> ConversationMessage | None: ...
    def list_for_conversation(
        self, business_id: str, conversation_id: str, *, limit: int | None = None
    ) -> tuple[ConversationMessage, ...]: ...
    def next_sequence(self, business_id: str, conversation_id: str) -> int: ...


class UnitOfWork(Protocol):
    businesses: BusinessRepository
    business_dna: BusinessDNARepository
    leads: LeadRepository
    cases: ProcessCaseRepository
    events: ProcessEventRepository
    idempotency: IdempotencyRepository
    conversations: ConversationRepository
    conversation_messages: ConversationMessageRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
