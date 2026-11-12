#!/usr/bin/env bash
set -euo pipefail

KERNEL_SERVICE=${1:-kernel}
shift || true
[[ $# -gt 0 ]] || set -- training
if [[ $# -eq 2 && $2 == /* ]]; then
  set -- "$1:$2"
fi
declare -A PROBE
MODULES=()
for spec in "$@"; do
  module=${spec%%:*}
  probe=/today
  [[ $spec == *:* ]] && probe=${spec#*:}
  PROBE[$module]=$probe
  MODULES+=("$module")
done

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUN_ID=${RUN_ID:-$$}
NET=arga-two-services-$RUN_ID
P=two-$RUN_ID
TAG=${IMAGE_TAG:-two-services-$RUN_ID}
PG_PASSWORD=postgres-de-prueba
KERNEL_PASSWORD=kernel-de-prueba
TOKEN=$(openssl rand -hex 32)
VERSION=v9.9.9
LOGS=$(mktemp -d)

cleanup() {
  [[ -n ${KEEP:-} ]] && return 0
  docker ps -aq --filter "network=$NET" | xargs -r docker rm -fv >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  if [[ -z ${IMAGE_TAG:-} ]]; then
    local images=("arga-kernel:$TAG")
    for module in "${MODULES[@]}"; do images+=("arga-$module:$TAG"); done
    docker rmi "${images[@]}" >/dev/null 2>&1 || true
  fi
  rm -rf "$LOGS"
}
trap cleanup EXIT

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FALLA: $*" >&2; exit 1; }

healthy() {
  local name=$1
  for _ in $(seq 1 90); do
    case $(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$name") in
      "running healthy") return 0 ;;
      exited*) break ;;
    esac
    sleep 2
  done
  docker logs "$name" 2>&1 | tail -15 | sed 's/^/  | /'
  echo "FALLA: $name no llegó a estar sano" >&2
  return 1
}

each() {
  local step=$1 limit=${2:-${#MODULES[@]}}
  local module failed=() start i
  for ((start = 0; start < ${#MODULES[@]}; start += limit)); do
    local pids=() batch=("${MODULES[@]:start:limit}")
    for module in "${batch[@]}"; do
      "$step" "$module" >"$LOGS/$module" 2>&1 &
      pids+=($!)
    done
    for i in "${!pids[@]}"; do
      wait "${pids[$i]}" || failed+=("${batch[$i]}")
    done
  done
  for module in "${MODULES[@]}"; do sed "s/^/  $module | /" "$LOGS/$module"; done
  [[ ${#failed[@]} -eq 0 ]] || fail "${failed[*]}"
}

credentials_key_var() { echo "${1^^}_CREDENTIALS_KEY"; }

HEALTH=(--health-cmd "python -c \"import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/readyz',timeout=5).status==200 else 1)\"" --health-interval 2s)

say "imágenes de este árbol"
if [[ -z ${IMAGE_TAG:-} ]]; then
  pids=()
  "$ROOT/scripts/build-image.sh" "$KERNEL_SERVICE/Dockerfile" "arga-kernel:$TAG" & pids+=($!)
  for module in "${MODULES[@]}"; do
    "$ROOT/scripts/build-image.sh" "modules/$module/Dockerfile" "arga-$module:$TAG" & pids+=($!)
  done
  for pid in "${pids[@]}"; do wait "$pid" || fail "no se construyó una imagen"; done
fi
echo "  arga-kernel:$TAG y ${MODULES[*]/#/arga-}"
for module in "${MODULES[@]}"; do
  docker image inspect "arga-$module:$TAG" >/dev/null 2>&1 || fail "falta la imagen arga-$module:$TAG"
done

say "el kernel ya no lleva dentro los manifiestos"
if docker run --rm --entrypoint sh "arga-kernel:$TAG" -c "test -e /opt/manifests" 2>/dev/null; then
  fail "la imagen del kernel sigue copiando los manifiestos de los módulos"
fi
echo "  /opt/manifests no existe en la imagen"

say "Postgres y los logins"
docker network create "$NET" >/dev/null
docker run -d --name "$P-postgres" --network "$NET" --network-alias postgres \
  -e POSTGRES_USER=arga -e POSTGRES_PASSWORD=$PG_PASSWORD -e POSTGRES_DB=arga \
  --tmpfs /var/lib/postgresql/data \
  --health-cmd "pg_isready -U arga -h 127.0.0.1" --health-interval 1s postgres:16-alpine >/dev/null
healthy "$P-postgres" || fail "Postgres"
passwords=(-e "KERNEL_DB_PASSWORD=$KERNEL_PASSWORD")
for module in "${MODULES[@]}"; do passwords+=(-e "${module^^}_DB_PASSWORD=$module-de-prueba"); done
docker run --rm --network "$NET" \
  -e ADMIN_DATABASE_URL=postgresql+asyncpg://arga:$PG_PASSWORD@postgres:5432/arga \
  "${passwords[@]}" "arga-kernel:$TAG" python -m kernel.roles | sed 's/^/  /'

say "el kernel arranca sin saber nada de los módulos"
docker run -d --name "$P-kernel" --network "$NET" --network-alias kernel \
  -e DATABASE_URL=postgresql+asyncpg://arga_kernel:$KERNEL_PASSWORD@postgres:5432/arga \
  -e MODULE_REGISTRATION_TOKEN="$TOKEN" -e APP_VERSION=$VERSION \
  "${HEALTH[@]}" "arga-kernel:$TAG" >/dev/null
healthy "$P-kernel" || fail "el kernel"
registered=$(docker run --rm --network "$NET" "arga-kernel:$TAG" \
  python -c "import httpx; print(len(httpx.get('http://kernel:8000/modules', timeout=30).json()))")
echo "  módulos registrados al arrancar el kernel: $registered"
[[ $registered == 0 ]] || fail "el kernel registró módulos por su cuenta"

without_secret() {
  local module=$1 key_var
  key_var=$(credentials_key_var "$module")
  if docker run --name "$P-$module-sin-secreto" --network "$NET" \
    -e DATABASE_URL=postgresql+asyncpg://svc_$module:$module-de-prueba@postgres:5432/arga \
    -e KERNEL_URL=http://kernel:8000 -e APP_VERSION=$VERSION -e "$key_var=$(openssl rand -hex 32)" \
    "arga-$module:$TAG" >/dev/null 2>&1; then
    echo "arrancó sin MODULE_REGISTRATION_TOKEN"
    return 1
  fi
  docker logs "$P-$module-sin-secreto" 2>&1 | tail -2 | sed 's/^/| /'
  docker rm -fv "$P-$module-sin-secreto" >/dev/null
}
say "sin el secreto, ningún módulo llega a servir"
each without_secret

with_secret() {
  local module=$1 key_var
  key_var=$(credentials_key_var "$module")
  docker run -d --name "$P-$module" --network "$NET" --network-alias "$module" \
    -e DATABASE_URL=postgresql+asyncpg://svc_$module:$module-de-prueba@postgres:5432/arga \
    -e KERNEL_URL=http://kernel:8000 -e MODULE_REGISTRATION_TOKEN="$TOKEN" -e APP_VERSION=$VERSION \
    -e "$key_var=$(openssl rand -hex 32)" "${HEALTH[@]}" "arga-$module:$TAG" >/dev/null
  healthy "$P-$module"
  docker logs "$P-$module" 2>&1 | grep -E "registrado|dueño|separado" | sed 's/^/| /' || true
}
say "con el secreto, cada módulo se registra a sí mismo, de ${STACK_PARALLEL:-4} en ${STACK_PARALLEL:-4}"
each with_secret "${STACK_PARALLEL:-4}"

say "lo que dice el kernel de ellos, y lo que sirven contra las tablas que acaba de crear"
args=()
for module in "${MODULES[@]}"; do args+=("$module:${PROBE[$module]}"); done
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import httpx, sys
probes = dict(arg.split(':', 1) for arg in sys.argv[1:])
registered = {m['id']: m for m in httpx.get('http://kernel:8000/modules', timeout=30).json()}
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'two-services-sintetico'}, timeout=30).json()['id']
bad = []
for module, probe in probes.items():
    m = registered.get(module)
    if not m:
        print(f'  {module}: no está registrado'); bad.append(module); continue
    ok = m['version'] == '$VERSION' and m['enabled']
    r = httpx.get(f'http://{module}:8000{probe}', headers={'x-arga-user': person}, timeout=30)
    print(f\"  {module}: version={m['version']} enabled={m['enabled']} scopes={m['scopes']} {probe}: {r.status_code}\")
    if not ok or r.status_code != 200:
        bad.append(module)
sys.exit(1 if bad else 0)
" "${args[@]}" || fail "el registro no dice lo que está corriendo, o un módulo no sirve tras registrarse"

say "OK: ${MODULES[*]} se registran en el kernel real y quedan listos para servir"
