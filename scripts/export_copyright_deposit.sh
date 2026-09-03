#!/usr/bin/env bash
# Build a copyright-deposit zip of this repository without git metadata or secrets.
# Run from the repository root. Does not upload anything.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
stamp="$(git rev-parse --short HEAD)"
out="${TMPDIR:-/tmp}/flywheel-copyright-deposit-${stamp}.zip"
git archive --format=zip --prefix="flywheel-ai-business-process-engine/" HEAD \
  -o "$out"
echo "$out"
echo "commit $(git rev-parse HEAD)"
echo "Upload this zip at copyright.gov. Do not add .env or ID documents to it."
