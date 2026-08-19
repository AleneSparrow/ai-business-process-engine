"""Diagnose (and optionally fix) a business's live `qualification.rules` --
written for the `test-law-firm` finding in `booking-milestone-and-research.md`:
a stale rule left over from an earlier manual test (adding a temporary
"General inquiry test" service to exercise the human_review path) made
*every* commercial path on that business escalate to a human before the
engine ever reached booking/quote/direct_step -- because `rules` are
evaluated in order and the first match wins (see
`QualificationService._qualification_rule_outcome`), so one overly-broad
leftover rule (e.g. matching on `service_id` `exists`, which is true for
every lead) silently shadows every rule after it, forever, for every future
lead -- not just the one it was written to test.

The Settings UI does not expose `qualification.rules` for editing (see
`BusinessDNASettingsService._apply`, which deliberately never touches
`rules` once any are configured, so it can't clobber a business's real
custom rules) -- so once a leftover test rule like this gets in, there is
currently no product-level way to see or remove it. This script is that way,
for exactly this kind of cleanup, until (if ever) `qualification.rules`
gets its own Settings editor.

Every write goes through `BusinessDNARepository.add_version` -- Business DNA
is versioned and immutable by design (same as every Settings save), so
--reset-rules never rewrites history: run `list_versions` (or check the
Business's version history however you normally do) if you ever need to see
or restore the version this replaced.

This talks directly to the database via DATABASE_URL and touches nothing
else -- same operating convention as scripts/grant_trial_access.py. It is
meant to be run by hand, by whoever owns DATABASE_URL (Alena), from a
machine that already has it configured -- it is never run by, or with
credentials shared to, an AI assistant.

Usage:
    # Read-only -- always start here. Prints the active version's qualification
    # config (rules, default_outcome, enforce_service_area) so you can see
    # exactly what's configured before touching anything.
    DATABASE_URL=postgresql://... python scripts/inspect_qualification_rules.py test-law-firm

    # Fix -- replaces qualification.rules with the same default the onboarding
    # builder (src/domain/business_dna_builder.py) would generate for this
    # business's *current* service-area setup, as a new Business DNA version.
    # Every other field in the configuration (services, pricing, booking,
    # communication, ...) is carried over byte-for-byte unchanged -- this only
    # touches qualification.rules.
    DATABASE_URL=postgresql://... python scripts/inspect_qualification_rules.py test-law-firm --reset-rules

    # Or, if you already have a shell with Railway's Postgres attached:
    railway run python scripts/inspect_qualification_rules.py test-law-firm
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.persistence.business_dna_settings_service import _deep_copy  # noqa: E402
from src.persistence.sqlalchemy_uow import (  # noqa: E402
    SQLAlchemyUnitOfWork,
    create_database_engine,
)

# Mirrors src/domain/business_dna_builder.py's build_business_dna() exactly --
# the same rule an onboarding business with an enforced service area gets on
# day one, and the same rule BusinessDNASettingsService._apply() would have
# auto-added had `rules` still been empty when a remote business last saved
# Settings. Keeping this one rule (rather than clearing to []) means the
# business keeps working the same way a freshly onboarded one would, instead
# of falling through to `default_outcome` for every lead.
_PRIMARY_AREA_ID = "primary"


def _default_rules(enforce_service_area: bool) -> list[dict]:
    if enforce_service_area:
        return [{"field": "service_area_id", "operator": "in", "value": [_PRIMARY_AREA_ID], "outcome": "qualified"}]
    return [{"field": "service_id", "operator": "exists", "value": True, "outcome": "qualified"}]


def _print_qualification(config: dict) -> None:
    qualification = config.get("qualification", {})
    print(f"  enforce_service_area: {qualification.get('enforce_service_area')}")
    print(f"  default_outcome:      {qualification.get('default_outcome')!r}")
    rules = qualification.get("rules", [])
    if not rules:
        print("  rules: (empty)")
    else:
        print(f"  rules ({len(rules)}, evaluated in order -- first match wins):")
        for index, rule in enumerate(rules, start=1):
            print(f"    {index}. {json.dumps(rule)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business_id", help="The business's id (e.g. test-law-firm)")
    parser.add_argument(
        "--reset-rules",
        action="store_true",
        help="Replace qualification.rules with the onboarding-equivalent default for this "
        "business's current enforce_service_area setting, as a new Business DNA version. "
        "Without this flag, the script only reads and prints -- nothing is written.",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set -- point it at the real database before running this.")

    engine = create_database_engine(database_url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)

    with factory() as unit_of_work:
        current = unit_of_work.business_dna.get_active(args.business_id)
        if current is None:
            raise SystemExit(f"No active Business DNA found for business {args.business_id!r}")

        print(f"Business:        {args.business_id}")
        print(f"Active version:  {current.version}")
        print("Current qualification config:")
        _print_qualification(current.configuration)

        if not args.reset_rules:
            print("\n(Read-only run -- pass --reset-rules to actually replace the rules above.)")
            return

        configuration = _deep_copy(current.configuration)
        enforce_service_area = bool(configuration.get("qualification", {}).get("enforce_service_area", False))
        new_rules = _default_rules(enforce_service_area)
        configuration["qualification"]["rules"] = new_rules

        print("\nReplacing with:")
        _print_qualification(configuration)

        new_version = unit_of_work.business_dna.add_version(args.business_id, configuration)
        unit_of_work.commit()
        print(f"\nDone -- new active version: {new_version.version} (previous version {current.version} is kept in history, not deleted).")


if __name__ == "__main__":
    main()
