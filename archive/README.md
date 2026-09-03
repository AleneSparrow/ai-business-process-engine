# Archive — frozen, out of scope for active work

This folder holds **historical, superseded, or one-off** material that is no
longer part of the live product but is kept for reference and history. Nothing
here is imported by `src/`, exercised by `tests/`, built into the app, or run
in CI.

**Access is intentionally restricted during ongoing work.** `archive/` is
listed in `.cursorignore`, so Cursor's indexing and agents do not read or edit
it; it is also excluded from pytest collection (`pytest.ini`) and from the
Docker build context (`.dockerignore`). Do not add live code or tests here, and
do not depend on anything in this folder from live code. To bring an item back
into use, move it out of `archive/` first.

## Contents

- `front/` — disconnected React/JSX/TSX UI mockups from August 2026. The live
  frontend is `web/app`.
- `docs/` — historical status / go-to-market snapshots, explicitly marked
  superseded or reconstructed. Current product context lives in `CLAUDE.md`,
  `README.md`, `DEPLOY.md`, and the maintained files under `docs/`.
- `reports/` — dated one-off live-evaluation output dumps (Aug 2026), including
  the rejected Haiku intent-caching experiment. The eval harness itself
  (`scripts/live_vertical_eval.py`) is kept live and can regenerate results.
- `scripts/` — retired one-off probes (e.g. `live_intent_field_diff.py`,
  self-marked "Retired 2026-08-25").
