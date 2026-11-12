#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
NET=arga-login-e2e
TAG=${E2E_TAG:-login-e2e}
STATE=$(mktemp -d)
PG_PASSWORD=postgres-de-prueba
KERNEL_PASSWORD=kernel-de-prueba
AUTH_PASSWORD=auth-de-prueba
ADMIN_PASSWORD=admin-de-prueba
WEB_SECRET=secreto-de-arga-web-de-prueba
SESSION_SECRET=secreto-de-sesion-de-prueba-bastante-largo
CONTAINERS=(e2e-postgres e2e-kernel e2e-auth e2e-gateway)

cleanup() {
  [[ -n ${E2E_KEEP:-} ]] && return 0
  docker rm -f "${CONTAINERS[@]}" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf "$STATE"
}
trap cleanup EXIT
E2E_KEEP= cleanup
mkdir -p "$STATE"

say() { printf '\n== %s\n' "$*"; }

if [[ -z ${E2E_SKIP_BUILD:-} ]]; then
  say "imágenes"
  for image in kernel gateway auth; do
    docker build -q -f "$ROOT/$image/Dockerfile" -t "arga-$image:$TAG" "$ROOT" >/dev/null
    echo "arga-$image:$TAG"
  done
fi

wait_healthy() {
  for _ in $(seq 1 90); do
    case $(docker inspect -f '{{.State.Health.Status}}' "$1" 2>/dev/null) in
      healthy) return 0 ;;
    esac
    [[ $(docker inspect -f '{{.State.Status}}' "$1") == exited ]] && break
    sleep 2
  done
  docker logs "$1" 2>&1 | tail -20
  echo "$1 no llegó a estar sano" >&2
  return 1
}

say "Postgres, roles, kernel y Keycloak"
docker network create "$NET" >/dev/null
docker run -d --name e2e-postgres --network "$NET" --network-alias postgres \
  -e POSTGRES_USER=arga -e POSTGRES_PASSWORD=$PG_PASSWORD -e POSTGRES_DB=arga \
  --health-cmd "pg_isready -U arga" --health-interval 2s postgres:16-alpine >/dev/null
wait_healthy e2e-postgres
docker run --rm --network "$NET" \
  -e ADMIN_DATABASE_URL=postgresql+asyncpg://arga:$PG_PASSWORD@postgres:5432/arga \
  -e KERNEL_DB_PASSWORD=$KERNEL_PASSWORD -e AUTH_DB_PASSWORD=$AUTH_PASSWORD \
  "arga-kernel:$TAG" python -m kernel.roles | tail -3
docker run -d --name e2e-kernel --network "$NET" --network-alias kernel \
  -e DATABASE_URL=postgresql+asyncpg://arga_kernel:$KERNEL_PASSWORD@postgres:5432/arga \
  "arga-kernel:$TAG" >/dev/null
docker run -d --name e2e-auth --network "$NET" --network-alias auth \
  -e KC_DB_URL=jdbc:postgresql://postgres:5432/arga -e KC_DB_USERNAME=arga_auth \
  -e KC_DB_PASSWORD=$AUTH_PASSWORD -e KC_DB_SCHEMA=auth -e KC_HTTP_ENABLED=true \
  -e KC_HOSTNAME_STRICT=false \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=$ADMIN_PASSWORD \
  "arga-auth:$TAG" >/dev/null
wait_healthy e2e-kernel
wait_healthy e2e-auth

kc() { docker exec -i e2e-auth /opt/keycloak/bin/kcadm.sh "$@"; }
kc config credentials --server http://localhost:8080/auth --realm master --user admin \
  --password $ADMIN_PASSWORD >/dev/null 2>&1

say "el realm como está hoy en producción: una persona sin correo, que conectó Claude"
kc create users -r arga -s username=dueno -s enabled=true >/dev/null 2>&1
owner_id=$(kc get users -r arga -q username=dueno -q exact=true --fields id --format csv --noquotes)
kc set-password -r arga --username dueno --new-password contraseña-de-prueba-1
echo "persona $owner_id"

say "y ya comparte un espacio: el gateway se lo pasará al kernel en cada petición (ADR-0038)"
docker exec e2e-kernel python -c "
import httpx
k = httpx.Client(base_url='http://localhost:8000', timeout=30)
person = k.post('/internal/users', json={'subject': '$owner_id'}).json()['id']
space = k.post('/internal/spaces', json={'name': 'Casa sintética'}, headers={'x-arga-user': person})
assert space.status_code == 201, space.text
print('espacio', space.json()['id'])
"

say "el IdP de mentira, en el papel de Google"
kc create realms -s realm=fake -s enabled=true >/dev/null 2>&1
kc create clients -r fake -s clientId=arga-broker -s secret=secreto-del-broker -s publicClient=false \
  -s 'redirectUris=["http://auth:8080/auth/realms/arga/broker/fake/endpoint"]' >/dev/null 2>&1
for person in dueno intruso; do
  kc create users -r fake -s "username=$person@ejemplo.com" -s "email=$person@ejemplo.com" \
    -s emailVerified=true -s enabled=true -s firstName=Prueba -s lastName=Sintetica >/dev/null 2>&1
  kc set-password -r fake --username "$person@ejemplo.com" --new-password contraseña-de-prueba-1
done

say "el cliente de Claude, confidencial y con secreto, como estaba antes de F4"
claude_id=$(kc get clients -r arga -q clientId=claude --fields id --format csv --noquotes)
kc update "clients/$claude_id" -r arga -s publicClient=false -s clientAuthenticatorType=client-secret \
  -s secret=secreto-viejo-de-claude
kc get "clients/$claude_id" -r arga --fields publicClient --format csv --noquotes | sed 's/^/público: /'

say "auth-sync, como en cada despliegue"
docker run --rm --network "$NET" --entrypoint /bin/bash \
  -e KC_ADMIN_PASSWORD=$ADMIN_PASSWORD -e ARGA_WEB_CLIENT_SECRET=$WEB_SECRET \
  -e GOOGLE_CLIENT_ID=id-de-google-de-prueba -e GOOGLE_CLIENT_SECRET=secreto-de-google-de-prueba \
  -e ARGA_ALLOWED_EMAILS="Dueno@Ejemplo.com=dueno" -e CLAUDE_RUN_CLIENT_SECRET=secreto-de-claude-run \
  "arga-auth:$TAG" /opt/arga/sync.sh

say "claude-run: confidencial, con su secreto, sus scopes opcionales y offline_access (ADR-0136)"
run_id=$(kc get clients -r arga -q clientId=claude-run --fields id --format csv --noquotes)
[ -n "$run_id" ] || { echo "FALLA: no está el cliente claude-run" >&2; exit 1; }
run_optional=$(kc get "clients/$run_id/optional-client-scopes" -r arga --fields name --format csv --noquotes)
for scope in offline_access outings:write insights:read; do
  grep -qxF "$scope" <<<"$run_optional" || { echo "FALLA: claude-run sin $scope opcional" >&2; exit 1; }
done
run_defaults=$(kc get "clients/$run_id/default-client-scopes" -r arga --fields name --format csv --noquotes)
if grep -q ':' <<<"$run_defaults"; then
  echo "FALLA: claude-run con un scope de módulo por defecto" >&2
  exit 1
fi
[ "$(kc get "clients/$run_id/client-secret" -r arga --fields value --format csv --noquotes)" = secreto-de-claude-run ] \
  || { echo "FALLA: claude-run sin el secreto de infra" >&2; exit 1; }
echo "  claude-run: $(wc -l <<<"$run_optional") scopes opcionales, offline_access entre ellos"

kc create identity-provider/instances -r arga -s alias=fake -s providerId=oidc -s enabled=true \
  -s trustEmail=true -s firstBrokerLoginFlowAlias=arga-primer-login \
  -s config.authorizationUrl=http://auth:8080/auth/realms/fake/protocol/openid-connect/auth \
  -s config.tokenUrl=http://auth:8080/auth/realms/fake/protocol/openid-connect/token \
  -s config.clientId=arga-broker -s config.clientSecret=secreto-del-broker \
  -s config.clientAuthMethod=client_secret_post -s config.syncMode=IMPORT \
  -s "config.defaultScope=openid email" -s config.validateSignature=false >/dev/null 2>&1
web_id=$(kc get clients -r arga -q clientId=arga-web --fields id --format csv --noquotes)
kc update "clients/$web_id" -r arga -s 'redirectUris=["http://gateway:8000/login/callback"]' \
  -s 'attributes."access.token.lifespan"=60'

gateway_env=(
  -e KERNEL_URL=http://kernel:8000 -e SHELL_URL=http://kernel:8000 -e AUTH_URL=http://auth:8080
  -e OAUTH_ISSUER=http://auth:8080/auth/realms/arga
  -e OAUTH_JWKS_URL=http://auth:8080/auth/realms/arga/protocol/openid-connect/certs
  -e MCP_RESOURCE_URL=http://localhost:8000/mcp
  -e OIDC_INTERNAL_URL=http://auth:8080/auth/realms/arga -e OIDC_CLIENT_ID=arga-web
  -e OIDC_CLIENT_SECRET=$WEB_SECRET -e PUBLIC_URL=http://gateway:8000 -e OIDC_IDP_HINT=fake
)

say "sin secreto de sesión, la imagen del gateway no arranca"
set +e
docker run --rm --network "$NET" "${gateway_env[@]}" "arga-gateway:$TAG" 2>&1 | grep -E "SESSION_SECRET|Application startup" | head -2
status=${PIPESTATUS[0]}
set -e
[[ $status -ne 0 ]] || { echo "FALLA: el gateway arrancó sin SESSION_SECRET" >&2; exit 1; }
echo "ok    salió con código $status"

docker run -d --name e2e-gateway --network "$NET" --network-alias gateway "${gateway_env[@]}" \
  -e SESSION_SECRET=$SESSION_SECRET "arga-gateway:$TAG" >/dev/null
wait_healthy e2e-gateway

drive() {
  docker run --rm --network "$NET" -v "$ROOT/scripts/login_e2e.py:/e2e/login_e2e.py:ro" \
    -v "$STATE:/state" --user "$(id -u)" "arga-gateway:$TAG" python /e2e/login_e2e.py "$@" /state
}

say "el navegador"
drive uno

say "lo que quedó en el realm y en el kernel"
known=$(docker exec e2e-postgres psql -At -U arga -d arga -c "select count(*) from kernel.users where subject = '$owner_id'")
[[ $known == 1 ]] && echo "ok    el kernel conoce a la persona por el sub que ya tenía Claude conectado" \
  || { echo "FALLA: el kernel no conoce el sub $owner_id" >&2; exit 1; }
owner_row=$(docker exec e2e-postgres psql -At -U arga -d arga -c \
  "select count(*) from kernel.ui_device_desktops d join kernel.users u on u.id = d.user_id where u.subject = '$owner_id' and d.device = 'mobile'")
[[ $owner_row == 1 ]] && echo "ok    lo que escribe desde el navegador lleva su persona (x-arga-user → GUC → user_id)" \
  || { echo "FALLA: la disposición escrita no lleva la persona del sub $owner_id" >&2; exit 1; }
people=$(kc get users -r arga --fields username --format csv --noquotes | sort | tr '\n' ' ')
[[ $people == "dueno " ]] && echo "ok    el intruso no ha creado a nadie en el realm" \
  || { echo "FALLA: en el realm hay: $people" >&2; exit 1; }
for path in /auth/admin/master/console/ /auth/realms/master/.well-known/openid-configuration; do
  status=$(docker run --rm --network "$NET" "arga-gateway:$TAG" python -c \
    "import httpx; print(httpx.get('http://gateway:8000$path', timeout=30).status_code)")
  [[ $status == 404 ]] && echo "ok    $path no se publica" \
    || { echo "FALLA: $path contesta $status" >&2; exit 1; }
done

say "se deshabilita a la persona en el realm"
kc update "users/$owner_id" -r arga -s enabled=false
drive dos

say "todo en orden"
