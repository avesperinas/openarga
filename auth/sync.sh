#!/bin/bash
set -euo pipefail

KCADM=/opt/keycloak/bin/kcadm.sh
SERVER=${KC_SERVER:-http://auth:8080/auth}
REALM=arga
CLIENT=claude
SCOPES=${SCOPES_FILE:-/opt/arga/client-scopes.ndjson}

: "${KC_ADMIN_PASSWORD:?KC_ADMIN_PASSWORD is required}"
: "${PUBLIC_URL:?PUBLIC_URL is required, e.g. https://openarga.example.com}"

render() {
  local out
  out=$(mktemp)
  sed "s#\${PUBLIC_URL}#${PUBLIC_URL%/}#g" "$1" >"$out"
  echo "$out"
}

login=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if login=$("$KCADM" config credentials --server "$SERVER" --realm master \
    --user "${KC_ADMIN_USER:-admin}" --password "$KC_ADMIN_PASSWORD" 2>&1); then
    login=""
    break
  fi
  echo "sync  Keycloak todavía no acepta el login de administrador (intento ${attempt})" >&2
  sleep 3
done
if [ -n "$login" ]; then
  echo "sync: no se pudo entrar en Keycloak como administrador: ${login##*$'\n'}" >&2
  exit 1
fi

client_id=$("$KCADM" get clients -r "$REALM" -q clientId="$CLIENT" --fields id --format csv --noquotes)
[ -n "$client_id" ] || { echo "sync: el cliente $CLIENT no existe en el realm $REALM" >&2; exit 1; }

scopes=""
load_scopes() {
  scopes=$("$KCADM" get client-scopes -r "$REALM" --fields id,name --format csv --noquotes)
}
load_scopes

scope_id() {
  local id name
  while IFS=, read -r id name; do
    [ "$name" = "$1" ] && echo "$id"
  done <<<"$scopes"
  return 0
}

defaults=$("$KCADM" get "clients/$client_id/default-client-scopes" -r "$REALM" --fields name --format csv --noquotes)
changes=0

while IFS= read -r line; do
  [ -n "$line" ] || continue
  name=$(sed -E 's/^\{"name": "([^"]+)".*/\1/' <<<"$line")

  if [ -z "$(scope_id "$name")" ]; then
    "$KCADM" create client-scopes -r "$REALM" -f - <<<"$line" >/dev/null 2>&1
    load_scopes
    echo "sync  creado    $name"
    changes=$((changes + 1))
  fi

  if [[ "$name" == *:* ]] && ! grep -qxF "$name" <<<"$defaults"; then
    "$KCADM" update "clients/$client_id/default-client-scopes/$(scope_id "$name")" -r "$REALM"
    echo "sync  asignado  $name a $CLIENT"
    changes=$((changes + 1))
  fi
done <"$SCOPES"

if [ "$("$KCADM" get "clients/$client_id" -r "$REALM" --fields publicClient --format csv --noquotes)" != true ]; then
  "$KCADM" update "clients/$client_id" -r "$REALM" -s publicClient=true -s 'attributes."pkce.code.challenge.method"=S256'
  echo "sync  público   $CLIENT, con PKCE y sin secreto"
  changes=$((changes + 1))
fi

optional=$("$KCADM" get "clients/$client_id/optional-client-scopes" -r "$REALM" --fields name --format csv --noquotes)
offline=$(scope_id offline_access)
if [ -n "$offline" ] && ! grep -qxF offline_access <<<"$optional"; then
  "$KCADM" update "clients/$client_id/optional-client-scopes/$offline" -r "$REALM"
  echo "sync  asignado  offline_access a $CLIENT, opcional"
  changes=$((changes + 1))
fi

WEB_CLIENT=arga-web
WEB_CLIENT_FILE=$(render "${WEB_CLIENT_FILE:-/opt/arga/client-arga-web.json}")
FLOW=arga-primer-login
: "${ARGA_WEB_CLIENT_SECRET:?falta ARGA_WEB_CLIENT_SECRET: sin él el gateway no puede cambiar códigos por tokens}"

web_id=$("$KCADM" get clients -r "$REALM" -q clientId="$WEB_CLIENT" --fields id --format csv --noquotes)
if [ -z "$web_id" ]; then
  "$KCADM" create clients -r "$REALM" -f "$WEB_CLIENT_FILE" >/dev/null 2>&1
  web_id=$("$KCADM" get clients -r "$REALM" -q clientId="$WEB_CLIENT" --fields id --format csv --noquotes)
  echo "sync  creado    cliente $WEB_CLIENT"
  changes=$((changes + 1))
fi
"$KCADM" update "clients/$web_id" -r "$REALM" -s "secret=$ARGA_WEB_CLIENT_SECRET"
web_defaults=$("$KCADM" get "clients/$web_id/default-client-scopes" -r "$REALM" --fields name --format csv --noquotes)
for name in basic email; do
  if ! grep -qxF "$name" <<<"$web_defaults"; then
    "$KCADM" update "clients/$web_id/default-client-scopes/$(scope_id "$name")" -r "$REALM"
    echo "sync  asignado  $name a $WEB_CLIENT"
    changes=$((changes + 1))
  fi
done

RUN_CLIENT=claude-run
RUN_CLIENT_FILE=$(render "${RUN_CLIENT_FILE:-/opt/arga/client-claude-run.json}")
if [ -n "${CLAUDE_RUN_CLIENT_SECRET:-}" ]; then
  run_id=$("$KCADM" get clients -r "$REALM" -q clientId="$RUN_CLIENT" --fields id --format csv --noquotes)
  if [ -z "$run_id" ]; then
    "$KCADM" create clients -r "$REALM" -f "$RUN_CLIENT_FILE" >/dev/null 2>&1
    run_id=$("$KCADM" get clients -r "$REALM" -q clientId="$RUN_CLIENT" --fields id --format csv --noquotes)
    echo "sync  creado    cliente $RUN_CLIENT"
    changes=$((changes + 1))
  fi
  "$KCADM" update "clients/$run_id" -r "$REALM" -s "secret=$CLAUDE_RUN_CLIENT_SECRET"
  run_optional=$("$KCADM" get "clients/$run_id/optional-client-scopes" -r "$REALM" --fields name --format csv --noquotes)
  while IFS= read -r line; do
    name=$(sed -E 's/^\{"name": "([^"]+)".*/\1/' <<<"$line")
    if [[ "$name" == *:* ]] && ! grep -qxF "$name" <<<"$run_optional"; then
      "$KCADM" update "clients/$run_id/optional-client-scopes/$(scope_id "$name")" -r "$REALM"
      echo "sync  asignado  $name a $RUN_CLIENT, opcional"
      changes=$((changes + 1))
    fi
  done <"$SCOPES"
  if [ -n "$offline" ] && ! grep -qxF offline_access <<<"$run_optional"; then
    "$KCADM" update "clients/$run_id/optional-client-scopes/$offline" -r "$REALM"
    echo "sync  asignado  offline_access a $RUN_CLIENT, opcional"
    changes=$((changes + 1))
  fi
fi

if ! "$KCADM" get authentication/flows -r "$REALM" --fields alias --format csv --noquotes | grep -xF "$FLOW" >/dev/null; then
  "$KCADM" create authentication/flows -r "$REALM" -s alias="$FLOW" -s providerId=basic-flow \
    -s topLevel=true -s builtIn=false \
    -s "description=Primer login desde un IdP: enlaza con una persona que ya existe, nunca crea" >/dev/null 2>&1
  echo "sync  creado    flujo $FLOW"
  changes=$((changes + 1))
fi
executions() {
  "$KCADM" get "authentication/flows/$FLOW/executions" -r "$REALM" --fields id,providerId,requirement --format csv --noquotes
}
for provider in idp-detect-existing-broker-user idp-auto-link; do
  if ! executions | cut -d, -f2 | grep -xF "$provider" >/dev/null; then
    "$KCADM" create "authentication/flows/$FLOW/executions/execution" -r "$REALM" -s "provider=$provider" >/dev/null 2>&1
  fi
done
while IFS=, read -r id provider requirement; do
  if [ "$requirement" != REQUIRED ]; then
    "$KCADM" update "authentication/flows/$FLOW/executions" -r "$REALM" \
      -b "{\"id\":\"$id\",\"requirement\":\"REQUIRED\"}"
    echo "sync  exigido   $provider en $FLOW"
    changes=$((changes + 1))
  fi
done < <(executions)

if [ -n "${GOOGLE_CLIENT_ID:-}" ] && [ -n "${GOOGLE_CLIENT_SECRET:-}" ]; then
  google=(-s enabled=true -s trustEmail=true -s "firstBrokerLoginFlowAlias=$FLOW"
    -s "config.clientId=$GOOGLE_CLIENT_ID" -s "config.clientSecret=$GOOGLE_CLIENT_SECRET"
    -s config.syncMode=IMPORT -s "config.defaultScope=openid email")
  if "$KCADM" get identity-provider/instances -r "$REALM" --fields alias --format csv --noquotes | grep -xF google >/dev/null; then
    "$KCADM" update identity-provider/instances/google -r "$REALM" "${google[@]}"
  else
    "$KCADM" create identity-provider/instances -r "$REALM" -s alias=google -s providerId=google "${google[@]}" >/dev/null 2>&1
    echo "sync  creado    IdP google"
    changes=$((changes + 1))
  fi
else
  echo "sync  sin GOOGLE_CLIENT_ID ni GOOGLE_CLIENT_SECRET: no hay login con Google" >&2
fi

if [ -n "${ARGA_ALLOWED_EMAILS+x}" ]; then
  allowed=()
  for entry in $(tr ',;' '  ' <<<"$ARGA_ALLOWED_EMAILS"); do
    username=""
    [[ "$entry" == *=* ]] && username=${entry#*=}
    allowed+=("$(tr '[:upper:]' '[:lower:]' <<<"${entry%%=*}")=$username")
  done
  if [ ${#allowed[@]} -eq 0 ]; then
    echo "sync: ARGA_ALLOWED_EMAILS está vacía; no se deshabilita a todo el mundo por un secreto vacío" >&2
    exit 1
  fi

  people=""
  load_people() {
    people=$("$KCADM" get users -r "$REALM" --offset 0 --limit 10000 --fields id,username,email,enabled,emailVerified --format csv --noquotes)
  }
  load_people
  users() { printf '%s\n' "$people"; }
  lower() { tr '[:upper:]' '[:lower:]' <<<"$1"; }
  by_email() {
    users | while IFS=, read -r id name mail on verified; do
      if [ "$(lower "$mail")" = "$1" ]; then echo "$id,$on,$verified"; fi
    done | sed -n 1p
  }
  without_email() {
    users | while IFS=, read -r id name mail on verified; do
      if [ "$name" = "$1" ] && [ -z "$mail" ]; then echo "$id"; fi
    done | sed -n 1p
  }

  created=0 enabled=0 disabled=0 linked=0
  for pair in "${allowed[@]}"; do
    email=${pair%%=*}
    username=${pair#*=}
    match=$(by_email "$email")
    if [ -z "$match" ] && [ -n "$username" ]; then
      id=$(without_email "$username")
      if [ -n "$id" ]; then
        "$KCADM" update "users/$id" -r "$REALM" -s "email=$email" -s emailVerified=true -s enabled=true
        echo "sync  enlazado  persona $id con su correo"
        load_people
        linked=$((linked + 1))
        continue
      fi
    fi
    if [ -z "$match" ]; then
      "$KCADM" create users -r "$REALM" -s "username=$email" -s "email=$email" -s emailVerified=true -s enabled=true >/dev/null 2>&1
      created=$((created + 1))
      load_people
      continue
    fi
    IFS=, read -r id on verified <<<"$match"
    if [ "$on" != true ] || [ "$verified" != true ]; then
      "$KCADM" update "users/$id" -r "$REALM" -s enabled=true -s emailVerified=true
      enabled=$((enabled + 1))
      load_people
    fi
  done

  emails=" ${allowed[*]%%=*} "
  while IFS=, read -r id name mail on verified; do
    mail=$(lower "$mail")
    if [ "$on" = true ] && { [ -z "$mail" ] || [[ "$emails" != *" $mail "* ]]; }; then
      "$KCADM" update "users/$id" -r "$REALM" -s enabled=false
      echo "sync  fuera     persona $id, no está en la lista blanca"
      disabled=$((disabled + 1))
    fi
  done < <(users)
  echo "sync  lista blanca · ${#allowed[@]} correo(s) · $created creada(s) · $linked enlazada(s) · $enabled habilitada(s) · $disabled deshabilitada(s)"
  changes=$((changes + created + linked + enabled + disabled))
else
  echo "sync  sin ARGA_ALLOWED_EMAILS: no se toca a nadie del realm" >&2
fi

echo "sync  realm $REALM al día · $changes cambio(s)"
