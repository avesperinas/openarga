#!/usr/bin/env bash
set -euo pipefail

# Test Postgres clusters, one per pytest worker.
#   eval "$(scripts/test-databases.sh up 4)"           with Docker
#   eval "$(scripts/test-databases.sh up 4 --local)"   with the local Postgres 16 binaries
#   scripts/test-databases.sh down [--local]

ACTION=${1:?up <n> [--local] | down [--local]}
RUN_ID=${RUN_ID:-$$}
PREFIX=arga-testdb-$RUN_ID
LOCAL=false
for argument in "$@"; do [[ $argument == --local ]] && LOCAL=true; done

if [[ $LOCAL == true ]]; then
  BIN=${PG_BIN:-$(ls -d /usr/lib/postgresql/16/bin 2>/dev/null || dirname "$(command -v initdb)")}
  ROOT_DIR=${TESTDB_DIR:-/var/tmp/openarga-testdb}
  as_postgres() {
    if [[ $(id -u) == 0 ]]; then su postgres -c "$*"; else bash -c "$*"; fi
  }
  local_down() {
    for dir in "$ROOT_DIR"/*; do
      [[ -d $dir ]] || continue
      as_postgres "$BIN/pg_ctl -D $dir stop -m immediate" >/dev/null 2>&1 || true
      rm -rf "$dir"
    done
  }
  case $ACTION in
    up)
      COUNT=${2:-1}
      local_down
      mkdir -p "$ROOT_DIR"
      [[ $(id -u) == 0 ]] && chown postgres "$ROOT_DIR"
      urls=()
      for n in $(seq 0 $((COUNT - 1))); do
        port=$((55432 + n))
        dir="$ROOT_DIR/$n"
        mkdir -p "$dir"
        [[ $(id -u) == 0 ]] && chown postgres "$dir"
        as_postgres "$BIN/initdb -D $dir -U openarga --auth=trust" >/dev/null
        as_postgres "$BIN/pg_ctl -D $dir -l $dir/log -o '-p $port -k /tmp -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200' start" >/dev/null
        for _ in $(seq 1 60); do
          "$BIN/pg_isready" -h 127.0.0.1 -p "$port" >/dev/null 2>&1 && break
          sleep 0.5
        done
        "$BIN/psql" -q -h 127.0.0.1 -p "$port" -U openarga -d postgres \
          -c "alter user openarga password 'changeme'" -c "create database openarga" >/dev/null
        urls+=("postgresql+asyncpg://openarga:changeme@127.0.0.1:$port/openarga")
      done
      printf 'export TEST_DATABASE_URLS=%q\n' "${urls[*]}"
      printf 'export TEST_DATABASE_URL=%q\n' "${urls[0]}"
      ;;
    down) local_down ;;
    *) echo "usage: $0 up <n> [--local] | down [--local]" >&2; exit 2 ;;
  esac
  exit 0
fi

down() {
  docker ps -aq --filter "label=arga.testdb=$RUN_ID" | xargs -r docker rm -fv >/dev/null 2>&1 || true
}

case $ACTION in
  up)
    COUNT=${2:-1}
    down
    for n in $(seq 0 $((COUNT - 1))); do
      docker run -d --name "$PREFIX-$n" --label "arga.testdb=$RUN_ID" \
        -e POSTGRES_USER=openarga -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=openarga \
        --tmpfs /var/lib/postgresql/data -p 127.0.0.1::5432 postgres:16-alpine \
        -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_connections=200 \
        >/dev/null
    done
    urls=()
    for n in $(seq 0 $((COUNT - 1))); do
      ready=""
      for _ in $(seq 1 60); do
        if docker exec "$PREFIX-$n" pg_isready -U openarga -h 127.0.0.1 >/dev/null 2>&1; then
          ready=1
          break
        fi
        sleep 0.5
      done
      [[ -n $ready ]] || { echo "test Postgres $PREFIX-$n did not start" >&2; exit 1; }
      port=$(docker port "$PREFIX-$n" 5432/tcp | head -1 | sed 's/.*://')
      urls+=("postgresql+asyncpg://openarga:changeme@127.0.0.1:$port/openarga")
    done
    printf 'export TEST_DATABASE_URLS=%q\n' "${urls[*]}"
    printf 'export TEST_DATABASE_URL=%q\n' "${urls[0]}"
    ;;
  down)
    down
    ;;
  *)
    echo "usage: $0 up <n> [--local] | down [--local]" >&2
    exit 2
    ;;
esac
