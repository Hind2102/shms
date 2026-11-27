#!/usr/bin/env bash
# Deploy the public demo to a Hugging Face Space (Docker SDK, CPU).
#
# NEEDS A PAID PLAN: since 2026 Hugging Face requires PRO for Docker Spaces; creating the Space on a free account
# returned 402 Payment Required (2026-11-27). Kept for a future paid plan; not used for v1.6.1.
#
#   hf auth login                       # once; the token stays in ~/.cache/huggingface, never in this repo
#   scripts/deploy_hf_space.sh          # default Space: Hind2102/shms-demo
#
# Builds a staging folder from the committed code (git archive, so nothing untracked or secret is uploaded),
# appends deploy/hf-space/Dockerfile.demo to the project Dockerfile, and uploads it. On the first run it creates the
# Space and sets SHMS_SECRET_KEY as a Space secret (random, never printed or stored locally).
set -euo pipefail
SPACE="${1:-Hind2102/shms-demo}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

git -C "$ROOT" archive HEAD pyproject.toml Dockerfile .dockerignore LICENSE shms | tar -x -C "$STAGE"
cat "$ROOT/deploy/hf-space/Dockerfile.demo" >> "$STAGE/Dockerfile"
cp "$ROOT/deploy/hf-space/README.md" "$STAGE/README.md"   # Space card (the image also reads it as the package readme)

hf auth whoami >/dev/null || { echo "Not logged in: run 'hf auth login' first." >&2; exit 1; }
if ! hf repos create "$SPACE" --repo-type space --space-sdk docker --public --exist-ok >/dev/null 2>&1; then
  echo "Could not create or find the Space $SPACE." >&2; exit 1
fi
if ! hf spaces secrets ls "$SPACE" 2>/dev/null | grep -q SHMS_SECRET_KEY; then
  # Random key, passed through the environment only: never printed, stored locally or put in shell history.
  SHMS_SECRET_KEY="$(openssl rand -base64 48 | tr -d '\n')" hf spaces secrets add "$SPACE" -s SHMS_SECRET_KEY >/dev/null
  echo "Space secret SHMS_SECRET_KEY set"
fi
hf upload "$SPACE" "$STAGE" . --repo-type space --commit-message "Deploy $(git -C "$ROOT" describe --tags --always)"
echo "Deployed. App: https://$(echo "$SPACE" | tr '[:upper:]/' '[:lower:]-').hf.space"
