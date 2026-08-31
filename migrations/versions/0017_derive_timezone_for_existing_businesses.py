"""Give existing businesses the time zone their own ZIP codes imply.

Migration 0013 noted it was the third time a behaviour change reached only new
signups. This is the fourth, and it is one I introduced: 8da7e67 started
deriving a business's time zone from the ZIP codes the wizard already collects,
but only inside build_business_dna -- so it applies to businesses created after
it and to nobody else.

Why that matters: the zone is printed to the customer in every slot offer and
every booking confirmation (commercial_service renders %Z). Both businesses on
production quote the wrong one -- riverside-home-repairs serves 90210/90211/
90212 (Pacific) and offers slots in CDT; test-law-firm serves 60601 (Central)
and confirms in PDT.

DELIBERATELY NARROWER THAN 0012 AND 0013. Those overwrote a stored value
outright, because the old value was a default nobody had chosen. A time zone is
different: Settings has always exposed it, so a stored value may be an owner's
considered choice, and silently moving someone's appointment times would be
worse than leaving them wrong. This touches only rows still carrying the
untouched previous default (America/New_York) on BOTH business.timezone and
booking.timezone, and only when the business's own postal codes imply something
else. Anything an owner has actually set is left alone.

Consequence, stated plainly: the two production businesses above are NOT
repaired here -- both hold values someone set. They need a deliberate decision,
not a guess. See claude/final-test-plan.md, block D.

(Originally written as 0016 and lost when a concurrent session claimed that
number; recreated as 0017. The lesson is in the loss, not the renumber: an
uncommitted file in a shared tree is a file that may not survive.)

Revision ID: 0017
Revises: 0016
"""

import json
import sys
from pathlib import Path
from typing import Any, Sequence

from alembic import op
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.domain.us_postal_timezones import (  # noqa: E402
    DEFAULT_TIMEZONE,
    timezone_for_service_area,
)


revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _loaded(configuration: Any) -> dict[str, Any] | None:
    if isinstance(configuration, dict):
        return configuration
    if isinstance(configuration, (str, bytes)):
        try:
            parsed = json.loads(configuration)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _postal_codes(configuration: dict[str, Any]) -> list[str]:
    areas = configuration.get("service_areas")
    if not isinstance(areas, list):
        return []
    codes: list[str] = []
    for area in areas:
        if not isinstance(area, dict) or area.get("type") != "postal_codes":
            continue
        for value in area.get("values", []) or []:
            if isinstance(value, (str, int)):
                codes.append(str(value))
    return codes


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
        business = configuration.get("business")
        booking = configuration.get("booking")
        if not isinstance(business, dict) or not isinstance(booking, dict):
            continue
        if business.get("timezone") != DEFAULT_TIMEZONE:
            continue
        if booking.get("timezone") != DEFAULT_TIMEZONE:
            continue
        derived = timezone_for_service_area(_postal_codes(configuration))
        if derived == DEFAULT_TIMEZONE:
            continue
        business["timezone"] = derived
        booking["timezone"] = derived
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

    Putting every derived zone back to Eastern would re-break exactly the
    businesses this fixed, and nothing records which rows changed. The schema
    is untouched by this revision, so Alembic still moves past it.
    """
