#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
NET=arga-desktop-e2e
TAG=desktop-e2e
PORT=${E2E_PORT:-18080}
OUT=${E2E_OUT:-$ROOT/desktop-e2e}
MODULES=(planner goals shopping)
PG_PASSWORD=postgres-test
KERNEL_PASSWORD=kernel-test
SESSION_SECRET=fake-session-secret-long-enough-to-pass
TOKEN=$(openssl rand -hex 32)
VERSION=v9.9.9

cleanup() {
  [[ -n ${KEEP:-} ]] && return 0
  docker ps -aq --filter "network=$NET" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
KEEP= cleanup

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

healthy() {
  local name=$1
  for _ in $(seq 1 90); do
    case $(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$name") in
      "running healthy") return 0 ;;
      exited*) break ;;
    esac
    sleep 2
  done
  docker logs "$name" 2>&1 | tail -20 | sed 's/^/  | /'
  fail "$name never became healthy"
}

READY=(--health-cmd "python -c \"import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/readyz',timeout=5).status==200 else 1)\"" --health-interval 2s)

say "images of this tree"
docker build -q -f "$ROOT/kernel/Dockerfile" -t "arga-kernel:$TAG" "$ROOT" >/dev/null
docker build -q -f "$ROOT/gateway/Dockerfile" -t "arga-gateway:$TAG" "$ROOT" >/dev/null
docker build -q -f "$ROOT/shell/Dockerfile" -t "arga-shell:$TAG" "$ROOT" >/dev/null
for module in "${MODULES[@]}"; do
  docker build -q -f "$ROOT/modules/$module/Dockerfile" -t "arga-$module:$TAG" "$ROOT" >/dev/null
done
echo "  kernel, gateway, shell y ${MODULES[*]}"

say "Postgres and the logins"
docker network create "$NET" >/dev/null
docker run -d --name e2e-desk-postgres --network "$NET" --network-alias postgres \
  -e POSTGRES_USER=arga -e POSTGRES_PASSWORD=$PG_PASSWORD -e POSTGRES_DB=arga \
  --health-cmd "pg_isready -U arga" --health-interval 2s postgres:16-alpine >/dev/null
healthy e2e-desk-postgres
passwords=()
for module in "${MODULES[@]}"; do passwords+=(-e "${module^^}_DB_PASSWORD=$module-test"); done
docker run --rm --network "$NET" \
  -e ADMIN_DATABASE_URL=postgresql+asyncpg://arga:$PG_PASSWORD@postgres:5432/arga \
  -e KERNEL_DB_PASSWORD=$KERNEL_PASSWORD "${passwords[@]}" \
  "arga-kernel:$TAG" python -m kernel.roles | sed 's/^/  /'

say "kernel"
docker run -d --name e2e-desk-kernel --network "$NET" --network-alias kernel \
  -e DATABASE_URL=postgresql+asyncpg://arga_kernel:$KERNEL_PASSWORD@postgres:5432/arga \
  -e MODULE_REGISTRATION_TOKEN="$TOKEN" -e APP_VERSION=$VERSION \
  "${READY[@]}" "arga-kernel:$TAG" >/dev/null
healthy e2e-desk-kernel

say "the apps, which register themselves"
for module in "${MODULES[@]}"; do
  docker run -d --name "e2e-desk-$module" --network "$NET" --network-alias "$module" \
    -e DATABASE_URL=postgresql+asyncpg://svc_$module:$module-test@postgres:5432/arga \
    -e KERNEL_URL=http://kernel:8000 -e MODULE_REGISTRATION_TOKEN="$TOKEN" -e APP_VERSION=$VERSION \
    -e "${module^^}_CREDENTIALS_KEY=$(openssl rand -hex 32)" \
    "${READY[@]}" "arga-$module:$TAG" >/dev/null
done
for module in "${MODULES[@]}"; do healthy "e2e-desk-$module"; echo "  $module listo"; done

say "shell y gateway"
docker run -d --name e2e-desk-shell --network "$NET" --network-alias shell \
  -e KERNEL_URL=http://kernel:8000 "arga-shell:$TAG" >/dev/null
for _ in $(seq 1 60); do
  docker exec e2e-desk-shell node -e "require('http').get('http://127.0.0.1:3000/',()=>process.exit(0)).on('error',()=>process.exit(1))" \
    2>/dev/null && break
  sleep 2
done
docker run -d --name e2e-desk-gateway --network "$NET" -p "127.0.0.1:$PORT:8000" \
  -e SESSION_SECRET=$SESSION_SECRET -e KERNEL_URL=http://kernel:8000 -e SHELL_URL=http://shell:3000 \
  -e OAUTH_ISSUER=http://auth.invalid/realms/arga -e OIDC_INTERNAL_URL=http://auth.invalid/realms/arga \
  -e OIDC_CLIENT_ID=arga-web -e OIDC_CLIENT_SECRET=test -e PUBLIC_URL=http://localhost:$PORT \
  "arga-gateway:$TAG" >/dev/null
healthy e2e-desk-gateway

say "a session sealed by the gateway"
cookie=$(docker run --rm -e SESSION_SECRET=$SESSION_SECRET "arga-gateway:$TAG" python -c "
import os, time
from dataclasses import asdict
from gateway.session import COOKIE, Sealer, Session
far = int(time.time()) + 86400
print(Sealer(os.environ['SESSION_SECRET']).seal(COOKIE, asdict(Session('desktop-e2e-sintetico', far, 'r', far))))
")
cookie_name=$(docker run --rm "arga-gateway:$TAG" python -c "from gateway.session import COOKIE; print(COOKIE)")

say "the desktop in the browser"
mkdir -p "$OUT"
E2E_URL="http://localhost:$PORT" E2E_COOKIE_NAME="$cookie_name" E2E_COOKIE="$cookie" E2E_OUT="$OUT" \
  uv run -q --with playwright --with httpx python "$ROOT/scripts/desktop_e2e.py"

say "OK: the desktop shows the real apps and the checkbox ticks through the gateway"
