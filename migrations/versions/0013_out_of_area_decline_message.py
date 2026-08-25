"""Give existing businesses the out-of-area decline wording.

Third time today the same shape of gap appeared, so it is worth naming: a
change that improves behaviour for NEW businesses reaches exactly zero of the
ones that already exist, because their Business DNA is stored, not recomputed.
Migration 0012 fixed it for the high-urgency escalation trigger; this does the
same for the decline message.

What it is for: the engine distinguishes four reasons for LOST, but every one
of them produced the same sentence -- "this request falls outside what we
currently support". A lead just outside the service area heard the wording a
business uses for a service it does not offer, and left without learning that a
different address was all it took. Out-of-area is the only LOST reason the
customer can act on, so it is the only one given its own wording (see
LeadIntakeService._lost_message).

Confirmed live on production 2026-08-25, deployment f8a6b508: a lead with a
Sacramento ZIP against a business serving 90210 still got the generic sentence,
because that business predates the field. That is the documented fallback
working correctly -- and exactly why this migration is needed.

Only fills the field where it is absent: a business that has already written
its own wording is left alone. Nothing here is customer data, only the
business's own approved copy.

Revision ID: 0013
Revises: 0012
"""

import json
from typing import Any, Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIELD = "lost_message_out_of_area"

# Kept in step with build_business_dna's default for new businesses. Duplicated
# rather than imported on purpose: a migration must keep doing what it did on
# the day it ran, even if the application's default is reworded later.
_MESSAGE = (
    "Sorry — that address is outside the area we currently serve. "
    "If you have another address nearby, send the ZIP code and "
    "we'll check it right away."
)


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
        qualification = configuration.get("qualification")
        if not isinstance(qualification, dict):
            continue
        existing = qualification.get(_FIELD)
        if isinstance(existing, str) and existing.strip():
            continue
        qualification[_FIELD] = _MESSAGE
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
    """Remove only the exact wording this migration wrote.

    A business that has since edited the message keeps its own text -- removing
    someone's copy because a revision is being rolled back would be worse than
    leaving a field they can see and change.
    """
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
        qualification = configuration.get("qualification")
        if not isinstance(qualification, dict):
            continue
        if qualification.get(_FIELD) != _MESSAGE:
            continue
        del qualification[_FIELD]
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
