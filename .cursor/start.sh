#!/usr/bin/env bash
# Per-boot runtime reconciliation. Starts the PostgreSQL 17 cluster, ensures
# the development role/databases exist, applies migrations, and seeds the
# example tenant. Idempotent and safe to re-run on every boot. Returns once
# the database is ready; the API and web dev server run as terminals.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DB_USER="ai_process_engine"
DB_PASS="local_development_only"
DB_NAME="ai_process_engine"
TEST_DB_NAME="ai_process_engine_test"

# --- Start the PostgreSQL cluster (systemd is not running in the VM) ---------
if ! sudo -u postgres pg_isready -q 2>/dev/null; then
  sudo pg_ctlcluster 17 main start
fi
# Wait for the socket to accept connections.
for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q 2>/dev/null; then break; fi
  sleep 1
done

# --- Ensure role and databases exist -----------------------------------------
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${TEST_DB_NAME}'" | grep -q 1 \
  || sudo -u postgres psql -c "CREATE DATABASE ${TEST_DB_NAME} OWNER ${DB_USER};"

# --- Migrate and seed --------------------------------------------------------
# shellcheck disable=SC1091
. .venv/bin/activate
export APP_ENV=development
export AI_PROVIDER=deterministic

DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}" \
  alembic upgrade head
DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASS}@localhost:5432/${TEST_DB_NAME}" \
  alembic upgrade head

DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}" \
  python examples/seed_example_business.py

echo "start.sh complete: PostgreSQL ready, migrations applied, example tenant seeded"
