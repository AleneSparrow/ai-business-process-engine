"""Drop the "high" escalation trigger from existing Business DNA.

Variant C (claude/unit-economics-and-urgency-default.md) decided that HIGH
urgency must no longer stop the sales cycle on arrival: the engine qualifies
the lead first and hands a complete card to a person afterwards. EMERGENCY is
untouched and still escalates immediately.

That decision was applied to `OnboardingInput.escalate_on_high_urgency`, to
the API schema and to the signup wizard -- all three of which only affect
businesses created FROM NOW ON. A business created earlier keeps
`human_escalation.triggers = ["high", "emergency"]` in its stored, active
Business DNA, and `AIIntentExtractor._configured_trigger_matches` reads that
stored list on every message. Confirmed live on production 2026-08-24
(deployment ce7c61f8): with the model's own requires_human flag correctly
suppressed, `riverside-home-repairs` still escalated a routine
"drain cleaning, ideally today" on message one -- purely from its stored
trigger. A NORMAL-urgency message on the same business went to QUALIFYING,
which isolates the trigger as the cause.

So without this migration the decision reaches exactly zero of the businesses
that already exist. Same class of gap as the earlier wizard/engine default
drift that `tests/test_onboarding_defaults_match_ui.py` now guards.

Deliberately in place, on the ACTIVE row only. A business that had
deliberately switched high-urgency escalation ON is indistinguishable here
from one that merely carried the old default, so this migration overrides
both. That is acceptable exactly once, and only now: there are no paying
customers yet. After launch the same change would have to separate a
deliberate setting from an inherited default, and would belong in the
application, not in a migration.

Revision ID: 0012
Revises: 0011
"""

import json
from typing import Any, Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER = "high"


def _loaded(configuration: Any) -> dict[str, Any] | None:
    """SQLite hands back a JSON string; Postgres hands back a parsed dict."""
    if isinstance(configuration, dict):
        return configuration
    if isinstance(configuration, (str, bytes)):
        try:
            parsed = json.loads(configuration)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT business_id, version, configuration FROM business_dna WHERE active"
        )
    ).fetchall()
    for business_id, version, raw_configuration in rows:
        configuration = _loaded(raw_configuration)
        if configuration is None:
            continue
        escalation = configuration.get("human_escalation")
        if not isinstance(escalation, dict):
            continue
        triggers = escalation.get("triggers")
        if not isinstance(triggers, list) or _TRIGGER not in triggers:
            continue
        escalation["triggers"] = [
            trigger for trigger in triggers if trigger != _TRIGGER
        ]
        connection.execute(
            sa.text(
                "UPDATE business_dna SET configuration = :configuration "
                "WHERE business_id = :business_id AND version = :version"
            ),
            {
                "configuration": json.dumps(configuration),
                "business_id": business_id,
                "version": version,
            },
        )


def downgrade() -> None:
    """Deliberately a no-op.

    Re-adding "high" to every active Business DNA would hand the trigger to
    businesses that never had it, which is worse than leaving the data as it
    is. The schema is unchanged by this revision, so a no-op downgrade still
    lets Alembic move past it to 0011 and earlier.
    """
