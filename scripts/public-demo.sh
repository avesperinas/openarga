#!/bin/bash
# Sets up, or brings up to date, a public OpenArga demo on Ubuntu 24.04 behind a Cloudflare Tunnel.
# Safe to run again: every step checks what is already there.
#
#   TUNNEL_TOKEN=<token> scripts/public-demo.sh <domain>
#   scripts/public-demo.sh <domain> <tunnel-token>
#   scripts/public-demo.sh --dry-run <domain>      print the steps, change nothing
#   scripts/public-demo.sh demo seed|day|reset|keep  what the cron jobs run
#
# The token is read from TUNNEL_TOKEN or the second argument (the environment keeps it out of the
# process list). Once the machine has a tunnel, running it again without a token keeps that one. It ends up only in a root-only file for the service, never in the repository or a log.
# Run it as a user with sudo. Nothing listens outside the machine: the gateway and Postgres bind
# 127.0.0.1 and the tunnel connects out.
#
# Variables: OPENARGA_DIR (default ~/openarga), OPENARGA_REPO, OPENARGA_REF (default main),
# DEMO_COPIES (default true: a copy of the cast per visitor, looked after every minute by
# `demo keep`; false: everyone shares the cast, with a new day at DEMO_DAY_AT and a reset at
# DEMO_RESET_AT, defaults "0 8" and "30 4", in Europe/Madrid time).
set -euo pipefail

DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY=1
  shift
fi

DIR=${OPENARGA_DIR:-$HOME/openarga}
REPO=${OPENARGA_REPO:-https://github.com/avesperinas/openarga.git}
REF=${OPENARGA_REF:-main}
RESET_AT=${DEMO_RESET_AT:-30 4}
DAY_AT=${DEMO_DAY_AT:-0 8}
COPIES=${DEMO_COPIES:-true}
LOG=${DEMO_LOG:-$HOME/openarga-demo.log}
TUNNEL_ENV=/etc/cloudflared/tunnel.env
MARK_BEGIN="# openarga public demo: begin"
MARK_END="# openarga public demo: end"

say() { printf '==> %s\n' "$*"; }
die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

run() {
  if ((DRY)); then
    printf '    $ %s\n' "$*"
  else
    "$@"
  fi
}

asroot() {
  if [[ $EUID -eq 0 ]]; then run "$@"; else run sudo "$@"; fi
}

write_file() {
  local path=$1 mode=$2 owner=$3 content
  content=$(cat)
  if ((DRY)); then
    printf '    write %s (mode %s, owner %s)\n' "$path" "$mode" "$owner"
    return
  fi
  if [[ -f $path ]] && [[ "$(cat "$path")" == "$content" ]]; then
    return
  fi
  printf '%s\n' "$content" | sudo_if_needed install -m "$mode" -o "${owner%%:*}" -g "${owner##*:}" /dev/stdin "$path"
}

sudo_if_needed() {
  if [[ $EUID -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

set_key() {
  local file=$1 key=$2 value=$3
  if ((DRY)); then
    printf '    set %s=%s in %s\n' "$key" "$value" "$file"
    return
  fi
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

set_yaml() {
  local file=$1 key=$2 value=$3
  if ((DRY)); then
    printf '    set %s: %s in %s\n' "$key" "$value" "$file"
    return
  fi
  if grep -q "^${key}:" "$file"; then
    sed -i "s|^${key}:.*|${key}: ${value}|" "$file"
  else
    printf '%s: %s\n' "$key" "$value" >>"$file"
  fi
}

compose_env() {
  # shellcheck disable=SC1091
  (
    cd "$DIR"
    set -a
    . ./.env
    set +a
    export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5433/${POSTGRES_DB}"
    "$@"
  )
}

demo_command() {
  local command=${1:-}
  case $command in
    seed | day | reset | keep) ;;
    *) die "usage: public-demo.sh demo seed|day|reset|keep" ;;
  esac
  export PATH="$HOME/.local/bin:$PATH"
  compose_env uv run python scripts/demo.py "$command"
}

if [[ "${1:-}" == "demo" ]]; then
  demo_command "${2:-}"
  exit 0
fi

DOMAIN=${1:-}
TOKEN=${TUNNEL_TOKEN:-${2:-}}
[[ -n $DOMAIN ]] || die "usage: [TUNNEL_TOKEN=...] public-demo.sh [--dry-run] <domain> [tunnel-token]"
[[ $DOMAIN =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$ ]] || die "not a host name: $DOMAIN"
[[ $COPIES == true || $COPIES == false ]] || die "DEMO_COPIES is true or false, not $COPIES"
tunnel_kept() {
  if [[ $EUID -eq 0 ]]; then test -s "$TUNNEL_ENV"; else sudo -n test -s "$TUNNEL_ENV" 2>/dev/null; fi
}
if [[ -z $TOKEN && $DRY -eq 0 ]] && ! tunnel_kept; then
  die "no tunnel token: set TUNNEL_TOKEN or pass it as the second argument"
fi
unset TUNNEL_TOKEN

preflight() {
  say "checking the machine"
  local os=unknown version=unknown
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os=${ID:-unknown}
    version=${VERSION_ID:-unknown}
  fi
  if [[ $os != ubuntu ]]; then
    if ((DRY)); then
      printf 'note: made for Ubuntu 24.04, this is %s\n' "$os"
    else
      die "made for Ubuntu 24.04, this is $os"
    fi
  elif [[ $version != 24.04 ]]; then
    printf 'warning: tested on Ubuntu 24.04, this is %s\n' "$version" >&2
  fi
  if [[ $EUID -ne 0 ]] && ! sudo -n true 2>/dev/null; then
    ((DRY)) || die "needs sudo without a password prompt, or run it as root"
  fi
  ARCH=$(dpkg --print-architecture 2>/dev/null || echo arm64)
  local memory
  memory=$(awk '/^(MemTotal|SwapTotal):/ {kb += $2} END {print int(kb / 1048576)}' /proc/meminfo 2>/dev/null || echo 0)
  if ((memory < 7)); then
    printf 'warning: %s GiB of memory and swap; building and running the stack wants 8 (add swap first)\n' "$memory" >&2
  fi
  CODENAME=${UBUNTU_CODENAME:-${VERSION_CODENAME:-noble}}
}

install_packages() {
  say "base packages"
  asroot apt-get update -qq
  asroot apt-get install -y -qq ca-certificates curl git gnupg openssl cron
}

install_docker() {
  if docker compose version >/dev/null 2>&1; then
    say "docker and the compose plugin are installed"
    return
  fi
  say "docker engine and the compose plugin, from Docker's apt repository"
  asroot install -m 0755 -d /etc/apt/keyrings
  asroot curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  asroot chmod a+r /etc/apt/keyrings/docker.asc
  write_file /etc/apt/sources.list.d/docker.sources 0644 root:root <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${CODENAME}
Components: stable
Architectures: ${ARCH}
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  asroot apt-get update -qq
  asroot apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  asroot systemctl enable --now docker
}

docker_command() {
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  else
    DOCKER=(sudo docker)
  fi
  if ((DRY)); then DOCKER=(docker); fi
}

install_uv() {
  export PATH="$HOME/.local/bin:$PATH"
  if command -v uv >/dev/null 2>&1; then
    say "uv is installed"
    return
  fi
  say "uv, the Python tool the scripts run with"
  if ((DRY)); then
    printf '    $ curl -LsSf https://astral.sh/uv/install.sh | sh\n'
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
}

fetch_repository() {
  if [[ -d $DIR/.git ]]; then
    say "updating $DIR to $REF"
    run git -C "$DIR" fetch --quiet origin "$REF"
    run git -C "$DIR" checkout --quiet "$REF"
    run git -C "$DIR" merge --quiet --ff-only "origin/$REF"
  else
    say "cloning $REPO into $DIR"
    run git clone --quiet --branch "$REF" "$REPO" "$DIR"
  fi
}

configure_instance() {
  say "instance for $DOMAIN"
  if [[ ! -f $DIR/openarga.yaml ]]; then
    run cp "$DIR/openarga.example.yaml" "$DIR/openarga.yaml"
  fi
  local yaml=$DIR/openarga.yaml
  set_yaml "$yaml" domain "$DOMAIN"
  set_yaml "$yaml" demo true
  set_yaml "$yaml" connections fake
  if ((DRY)); then
    printf '    ai: provider none stays as the example has it\n'
  elif ! grep -qE '^  provider: none' "$yaml"; then
    die "openarga.yaml: ai.provider must be none for the public demo"
  fi

  if [[ ! -f $DIR/.env ]]; then
    say "generating .env with new secrets"
    if ((DRY)); then
      printf '    $ scripts/stack-env.sh > %s/.env\n' "$DIR"
    else
      (umask 077 && "$DIR/scripts/stack-env.sh" >"$DIR/.env")
    fi
  fi
  local env=$DIR/.env
  set_key "$env" OPENARGA_DEMO true
  set_key "$env" OPENARGA_DEMO_COPIES "$COPIES"
  set_key "$env" PUBLIC_URL "https://$DOMAIN"
  set_key "$env" AUTH_ISSUER "https://$DOMAIN/auth/realms/arga"
  set_key "$env" MCP_PUBLIC_URL "https://$DOMAIN/mcp"
  run chmod 600 "$DIR/.env"

  write_file "$DIR/docker-compose.override.yml" 0644 "$(id -un):$(id -gn)" <<'EOF'
services:
  postgres:
    ports: !override ["127.0.0.1:5433:5432"]
  gateway:
    ports: !override ["127.0.0.1:8000:8000"]
EOF
  if ((DRY)); then
    printf '    exclude docker-compose.override.yml from git in %s\n' "$DIR"
  else
    grep -qxF docker-compose.override.yml "$DIR/.git/info/exclude" 2>/dev/null ||
      echo docker-compose.override.yml >>"$DIR/.git/info/exclude"
  fi
}

start_stack() {
  say "building and starting the stack"
  if ((DRY)); then
    printf '    $ (cd %s && uv run python scripts/compose.py)\n' "$DIR"
    printf '    $ (cd %s && docker compose up -d --build --wait --wait-timeout 1800)\n' "$DIR"
    return
  fi
  (cd "$DIR" && uv run python scripts/compose.py)
  (cd "$DIR" && "${DOCKER[@]}" compose up -d --build --wait --wait-timeout 1800)
}

wait_healthy() {
  local waiting
  for _ in $(seq 1 60); do
    waiting=$(cd "$DIR" && "${DOCKER[@]}" compose ps --format '{{.Service}} {{.Health}}' |
      awk '$2 != "" && $2 != "healthy" {print $1}')
    [[ -z $waiting ]] && return 0
    sleep 10
  done
  die "services still not healthy after ten minutes: $(echo "$waiting" | tr '\n' ' ')"
}

seed_demo() {
  say "seeding the cast"
  if ((DRY)); then
    printf '    wait until every service is healthy, then up to 3 tries of:\n'
    printf '    $ %s demo seed\n' "$0"
    if [[ $COPIES == true ]]; then
      printf '    $ %s demo keep    (the first copies for visitors)\n' "$0"
    fi
    return
  fi
  local attempt
  for attempt in 1 2 3; do
    wait_healthy
    if demo_command seed && { [[ $COPIES == false ]] || demo_command keep; }; then
      return 0
    fi
    printf 'seeding failed (attempt %s of 3), trying again in 30 s\n' "$attempt" >&2
    sleep 30
  done
  die "seeding failed three times; see the output above"
}

madrid_job() {
  local minute hour
  read -r minute hour <<<"$1"
  # shellcheck disable=SC2016
  printf '%s * * * * [ "$(TZ=Europe/Madrid date +\\%%H)" = %02d ] && "%s" demo %s >>"%s" 2>&1\n' \
    "$minute" "$((10#$hour))" "$2" "$3" "$LOG"
}

install_cron() {
  local script=$DIR/scripts/public-demo.sh block
  if [[ $COPIES == true ]]; then
    say "cron: every minute, drop the copies nobody uses and make ready ones"
    block=$(
      cat <<EOF
$MARK_BEGIN
* * * * * flock -n /tmp/openarga-demo-keep.lock "$script" demo keep >>"$LOG" 2>&1
$MARK_END
EOF
    )
  else
    say "cron: a new simulated day, and the nightly reset (Europe/Madrid time)"
    # Ubuntu's cron ignores CRON_TZ: each job runs hourly and only goes on in its Madrid hour.
    block=$(
      cat <<EOF
$MARK_BEGIN
$(madrid_job "$DAY_AT" "$script" day)
$(madrid_job "$RESET_AT" "$script" reset)
$MARK_END
EOF
    )
  fi
  if ((DRY)); then
    printf '    crontab block:\n%s\n' "$block" | sed 's/^/      /'
    return
  fi
  local current
  current=$(crontab -l 2>/dev/null || true)
  current=$(printf '%s\n' "$current" | sed "/^${MARK_BEGIN}\$/,/^${MARK_END}\$/d")
  printf '%s\n%s\n' "$current" "$block" | sed '/./,$!d' | crontab -
  sudo_if_needed systemctl enable --now cron
}

install_cloudflared() {
  if ! command -v cloudflared >/dev/null 2>&1; then
    say "cloudflared, from Cloudflare's apt repository"
    asroot install -m 0755 -d /usr/share/keyrings
    asroot curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
    write_file /etc/apt/sources.list.d/cloudflared.list 0644 root:root <<EOF
deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main
EOF
    asroot apt-get update -qq
    asroot apt-get install -y -qq cloudflared
  else
    say "cloudflared is installed"
  fi

  say "tunnel service"
  asroot install -m 0755 -d /etc/cloudflared
  if [[ -z $TOKEN ]]; then
    printf '    keeping the tunnel token already in %s\n' "$TUNNEL_ENV"
  elif ((DRY)); then
    printf '    write %s (mode 600, owner root) with the token\n' "$TUNNEL_ENV"
  else
    printf 'TUNNEL_TOKEN=%s\n' "$TOKEN" | write_file "$TUNNEL_ENV" 0600 root:root
  fi
  write_file /etc/systemd/system/cloudflared.service 0644 root:root <<'EOF'
[Unit]
Description=Cloudflare Tunnel for the OpenArga demo
After=network-online.target docker.service
Wants=network-online.target

[Service]
EnvironmentFile=/etc/cloudflared/tunnel.env
ExecStart=/usr/bin/cloudflared --no-autoupdate tunnel run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  asroot systemctl daemon-reload
  asroot systemctl enable cloudflared
  asroot systemctl restart cloudflared
}

verify() {
  say "checking"
  if ((DRY)); then
    printf '    $ curl http://127.0.0.1:8000/healthz\n    $ curl https://%s/healthz\n' "$DOMAIN"
    return
  fi
  curl -fsS --retry 10 --retry-delay 3 --retry-connrefused http://127.0.0.1:8000/healthz >/dev/null &&
    printf 'gateway answers on 127.0.0.1:8000\n'
  if curl -fsS --retry 10 --retry-delay 5 "https://$DOMAIN/healthz" >/dev/null 2>&1; then
    printf 'https://%s answers through the tunnel\n' "$DOMAIN"
  else
    printf 'https://%s does not answer yet: in Cloudflare, the tunnel needs a public hostname for it that points at http://localhost:8000\n' "$DOMAIN" >&2
  fi
}

preflight
install_packages
install_docker
docker_command
install_uv
fetch_repository
configure_instance
start_stack
seed_demo
install_cron
install_cloudflared
verify
say "done: https://$DOMAIN"
