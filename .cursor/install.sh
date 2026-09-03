#!/usr/bin/env bash
# Idempotent dependency bootstrap for the AI Business Process Engine.
# Runs after the repository is checked out. Installs the system toolchain
# (PostgreSQL 17 + Python 3.11 to match CI and the Dockerfile), the Python
# virtualenv, and the frontend dependencies. Per-boot service startup,
# database migration, and seeding live in start.sh instead.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export DEBIAN_FRONTEND=noninteractive

# --- System packages (PostgreSQL 17 + Python 3.11) ---------------------------
# PostgreSQL 17 matches docker-compose.yml / CI (postgres:17-alpine); the
# Ubuntu default is older, so pull it from the official PGDG apt repository.
if [ ! -f /etc/apt/sources.list.d/pgdg.list ]; then
  sudo install -d /usr/share/postgresql-common/pgdg
  sudo curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" \
    | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
fi

# Python 3.11 is the version CI and the Dockerfile pin; deadsnakes provides it
# on Ubuntu 24.04 (which ships 3.12 by default). add-apt-repository is itself
# idempotent, but skip it when the source is already present.
if ! ls /etc/apt/sources.list.d/ 2>/dev/null | grep -q deadsnakes; then
  sudo add-apt-repository -y ppa:deadsnakes/ppa
fi

sudo apt-get update -qq
sudo apt-get install -y -qq \
  postgresql-17 postgresql-client-17 \
  python3.11 python3.11-venv python3.11-dev \
  build-essential libpq-dev

# --- Backend Python virtualenv ----------------------------------------------
if [ ! -x .venv/bin/python ] || ! .venv/bin/python --version 2>&1 | grep -q '3.11'; then
  rm -rf .venv
  python3.11 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt

# --- Frontend dependencies ---------------------------------------------------
(
  cd web/app
  npm ci
  # Point the dev server at the local API if not already configured.
  [ -f .env.local ] || cp .env.example .env.local
)

echo "install.sh complete"
