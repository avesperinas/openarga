#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(node -p "require('$ROOT/packages/ui/package.json').devDependencies['playwright-core']")
OUT=${SHOTS_DIR:-$ROOT/storybook-shots}
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

(cd "$ROOT/packages/ui" && npx storybook build -o "$BUILD" --quiet >/dev/null)
rm -rf "$OUT"
mkdir -p "$OUT"
docker run --rm --ipc=host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$ROOT:$ROOT:ro" -v "$BUILD:/storybook:ro" -w "$ROOT/packages/ui" \
  "mcr.microsoft.com/playwright:v$VERSION-noble" \
  sh -c 'node scripts/shots.mjs /storybook /tmp/shots >&2 && tar -C /tmp/shots -cf - .' |
  tar -C "$OUT" -xf -
