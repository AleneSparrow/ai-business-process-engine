"""Fast, dependency-free unit coverage for Conversation.set_status's
transition table -- deliberately kept separate from tests/test_conversations.py
(which needs sqlalchemy+fastapi) so this layer can be exercised even in an
environment where those aren't installed.

Regression context (live finding, 2026-08-19): ConversationService.
_maybe_reactivate_lost_case (see src/persistence/conversation_service.py)
reopens a closed conversation with conversation.set_status(AI_ACTIVE, ...)
after reactivating its LOST case. The "LOST dead end" fix that added that
call was hand-traced against state_machine.py's ProcessState transitions
(LOST -> REACTIVATION -> CONTACTED) and looked correct there -- but it never
checked this *separate* ConversationStatus transition table, which still
treated CLOSED as fully terminal. The result: every single LOST-then-follow-up
message crashed with a 500 (ValueError: invalid conversation status
transition: closed -> ai_active) instead of ever reactivating, confirmed live
against the production widget-demo conversation API.
"""

from datetime import datetime, timezone

import pytest

from src.domain.conversations import Conversation, ConversationStatus


def _conversation(status: ConversationStatus) -> Conversation:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Conversation(
        conversation_id="conv-1",
        business_id="biz-1",
        token_hash="a" * 64,
        channel="webchat",
        status=status,
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        token_expires_at=now.replace(year=2027),
    )


def test_closed_conversation_can_be_reopened_to_ai_active() -> None:
    """The reactivation path this whole file exists to guard: LOST-case
    reactivation must be able to flip a CLOSED conversation back to
    AI_ACTIVE without raising."""
    conversation = _conversation(ConversationStatus.CLOSED)
    conversation.set_status(ConversationStatus.AI_ACTIVE, datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert conversation.status is ConversationStatus.AI_ACTIVE


@pytest.mark.parametrize(
    "target",
    [ConversationStatus.HUMAN_TAKEOVER_REQUESTED, ConversationStatus.HUMAN_TAKEOVER_ACTIVE],
)
def test_closed_conversation_still_rejects_every_other_transition(target: ConversationStatus) -> None:
    """CLOSED -> AI_ACTIVE is the one narrow exception added for
    reactivation -- every other target must still be rejected, so a
    genuinely terminal conversation (CANCELLED/PAID/COMPLETED cases, a
    finished human takeover) can't be reopened some other way."""
    conversation = _conversation(ConversationStatus.CLOSED)
    with pytest.raises(ValueError, match="invalid conversation status transition"):
        conversation.set_status(target, datetime(2026, 1, 2, tzinfo=timezone.utc))


def test_ai_active_conversation_can_move_to_human_takeover_active() -> None:
    """Staff reply from Conversations is an explicit takeover; the engine
    must not keep answering that session."""
    conversation = _conversation(ConversationStatus.AI_ACTIVE)
    conversation.set_status(
        ConversationStatus.HUMAN_TAKEOVER_ACTIVE, datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    assert conversation.status is ConversationStatus.HUMAN_TAKEOVER_ACTIVE
