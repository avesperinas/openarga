#!/bin/bash
# Boots the generated stack with throwaway secrets and checks every service is healthy.
#   scripts/stack-check.sh                      the example instance
#   scripts/stack-check.sh path/to/openarga.yaml another instance
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
CONFIG=${1:-$ROOT/openarga.example.yaml}
WORK=$(mktemp -d)
FILE=$ROOT/docker-compose.check.yml
PROJECT=arga-stack-check

compose() { docker compose -p "$PROJECT" -f "$FILE" --env-file "$WORK/.env" "$@"; }
cleanup() {
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$WORK" "$FILE"
}
trap cleanup EXIT

uv run python "$ROOT/scripts/compose.py" --config "$CONFIG" --output "$FILE"
"$ROOT/scripts/stack-env.sh" >"$WORK/.env"
grep -q '^OPENARGA_ADMIN_PASSWORD=.' "$WORK/.env"

compose up -d --build --wait --wait-timeout 600

unhealthy=$(compose ps --format '{{.Service}} {{.Health}}' | awk '$2 != "healthy" && $2 != "" {print}')
if [ -n "$unhealthy" ]; then
  echo "FAIL: not healthy:" >&2
  echo "$unhealthy" >&2
  compose logs --tail 40 >&2
  exit 1
fi

for service in $(compose config --services); do
  case "$service" in
    postgres|roles|auth|auth-sync|shell|*-worker) continue ;;
  esac
  compose exec -T "$service" python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" \
    || { echo "FAIL: $service /healthz" >&2; exit 1; }
  echo "ok  $service /healthz"
done
curl -fsS http://localhost:8000/healthz >/dev/null && echo "ok  gateway from the host"
