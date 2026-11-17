#!/usr/bin/env bash

# shellcheck disable=SC2016
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUN_ID=${RUN_ID:-$$}
NET=arga-backup-e2e-$RUN_ID
TAG=backup-e2e-$RUN_ID
PG=$NET-pg
ADMIN=argaadmin
DB=arga
PG_PASSWORD=postgres-test
KERNEL_PASSWORD=kernel-test
BACKUP_PASSWORD=backup-test
RESTIC_PASSWORD=restic-test

cleanup() {
  [[ -n ${KEEP:-} ]] && return 0
  docker ps -aq --filter "network=$NET" | xargs -r docker rm -fv >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker volume rm "$NET-backups" >/dev/null 2>&1 || true
}
trap 'cleanup; [[ -n ${KEEP:-} ]] || docker rmi "arga-kernel:$TAG" "arga-backup:$TAG" >/dev/null 2>&1 || true' EXIT
cleanup

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

say "images of this tree"
"$ROOT/scripts/build-image.sh" kernel/Dockerfile "arga-kernel:$TAG"
"$ROOT/scripts/build-image.sh" backup/Dockerfile "arga-backup:$TAG"
docker network create --internal "$NET" >/dev/null
docker volume create "$NET-backups" >/dev/null

say "Postgres, the backup login and the kernel schema"
docker run -d --name "$PG" --network "$NET" --network-alias postgres \
  -e POSTGRES_USER=$ADMIN -e POSTGRES_PASSWORD=$PG_PASSWORD -e POSTGRES_DB=$DB \
  postgres:16-alpine >/dev/null
for _ in $(seq 1 60); do
  docker logs "$PG" 2>&1 | grep 'init process complete' >/dev/null \
    && docker exec "$PG" pg_isready -U $ADMIN -q && break
  sleep 1
done
kernel() {
  docker run --rm --network "$NET" "$@"
}
kernel -e ADMIN_DATABASE_URL="postgresql+asyncpg://$ADMIN:$PG_PASSWORD@postgres:5432/$DB" \
  -e KERNEL_DB_PASSWORD=$KERNEL_PASSWORD -e BACKUP_DB_PASSWORD=$BACKUP_PASSWORD \
  "arga-kernel:$TAG" python -m kernel.roles
kernel -e DATABASE_URL="postgresql+asyncpg://arga_kernel:$KERNEL_PASSWORD@postgres:5432/$DB" \
  "arga-kernel:$TAG" python -m kernel.migrate

psql() { docker exec -i "$PG" psql -X -q -v ON_ERROR_STOP=1 -U $ADMIN -d $DB "$@"; }
psql <<'SQL'
insert into kernel.users (subject) values ('sintetico-1'), ('sintetico-2');
create role mod_probe nologin;
create schema probe authorization mod_probe;
create table probe.readings (
  id serial primary key,
  user_id uuid not null,
  value double precision,
  taken_at timestamptz not null default now(),
  note text
);
alter table probe.readings owner to mod_probe;
comment on table probe.readings is 'arga:person';
alter table probe.readings enable row level security;
alter table probe.readings force row level security;
create policy readings_owner on probe.readings
  using (user_id = nullif(current_setting('arga.user_id', true), '')::uuid);
insert into probe.readings (user_id, value, note)
select (select id from kernel.users order by subject limit 1), g / 3.0, 'fila ' || g
from generate_series(1, 5000) g;
SQL

CAPS=(--cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add SETUID --cap-add SETGID
  --security-opt no-new-privileges)
BACKUP=(docker run --rm "${CAPS[@]}" --network "$NET" -v "$NET-backups:/backups"
  -e "PGDATABASE=$DB" -e "PGPASSWORD=$BACKUP_PASSWORD" -e "RESTIC_PASSWORD=$RESTIC_PASSWORD"
  -e OFFSITE_REPOSITORY=/backups/offsite -e APP_VERSION=v9.9.9)

say "the backup does not see less because of RLS and cannot write"
seen=$(docker run --rm --network "$NET" -e PGPASSWORD=$BACKUP_PASSWORD --entrypoint psql "arga-backup:$TAG" \
  -X -At -h postgres -U arga_backup -d $DB -c 'select count(*) from probe.readings')
[[ $seen == 5000 ]] || fail "arga_backup sees $seen rows of 5000"
refused=$(docker run --rm --network "$NET" -e PGPASSWORD=$BACKUP_PASSWORD --entrypoint psql "arga-backup:$TAG" \
  -X -At -h postgres -U arga_backup -d $DB -c 'delete from probe.readings' 2>&1 || true)
echo "$refused"
grep -q 'permission denied' <<<"$refused" || fail "arga_backup ha podido borrar"
echo "OK: it sees the 5000 rows and a delete gives permission denied"

say "a backup, to both repositories"
"${BACKUP[@]}" "arga-backup:$TAG" once

say "test restore from the offsite one"
"${BACKUP[@]}" "arga-backup:$TAG" verify

say "another backup after changing data: it deduplicates and still restores the latest"
psql -c "update probe.readings set note = 'cambiada' where id <= 10"
"${BACKUP[@]}" "arga-backup:$TAG" once
"${BACKUP[@]}" "arga-backup:$TAG" status
"${BACKUP[@]}" "arga-backup:$TAG" verify

say "if the offsite one is misconfigured, the local backup still happens"
latest() { "${BACKUP[@]}" --entrypoint sh "arga-backup:$TAG" -c 'restic -r /backups/restic snapshots latest --host arga --json | grep -o "\"time\":\"[^\"]*\""'; }
before=$(latest)
if "${BACKUP[@]}" -e OFFSITE_REPOSITORY=s3:https://r2.invalid "arga-backup:$TAG" once; then
  fail "once accepted an impossible upload"
fi
after=$(latest)
[[ $after != "$before" ]] || fail "without the offsite one there was no local backup either"
echo "OK: the upload fails and there is a new local backup ($before -> $after)"

say "check of both repositories"
"${BACKUP[@]}" "arga-backup:$TAG" check

say "the prune: what no backup uses any more is deleted, even if the hourly backup already forgot it"
"${BACKUP[@]}" --entrypoint bash "arga-backup:$TAG" -c '
  set -euo pipefail
  mkdir -p /backups/work/dump && head -c 20000000 /dev/urandom > /backups/work/dump/ruido
  for repo in /backups/restic /backups/offsite; do
    id=$(restic -r $repo backup --host arga --json /backups/work/dump | grep -o "\"snapshot_id\":\"[^\"]*\"" | cut -d\" -f4)
    restic -q -r $repo forget "$id" >/dev/null
  done
  rm -rf /backups/work/dump
'
sizes() { "${BACKUP[@]}" --entrypoint sh "arga-backup:$TAG" -c 'du -sm /backups/restic /backups/offsite | cut -f1 | paste -sd " "'; }
measured() { "${BACKUP[@]}" "arga-backup:$TAG" space 2>&1 | sed -n 's/.*offsite uses \([0-9]*\)\..* MB of.*/\1/p'; }
read -r local_before offsite_before <<<"$(sizes)"
space_before=$(measured)
echo "before the prune: local $local_before MB, offsite $offsite_before MB; space says $space_before MB"
((space_before >= 20)) || fail "space does not count what waits for the prune ($space_before MB)"
"${BACKUP[@]}" "arga-backup:$TAG" daily
read -r local_after offsite_after <<<"$(sizes)"
space_after=$(measured)
echo "after: local $local_after MB, offsite $offsite_after MB; space says $space_after MB"
((local_before - local_after >= 15)) || fail "the prune deleted nothing locally"
((offsite_before - offsite_after >= 15)) || fail "the prune deleted nothing offsite"
((space_before - space_after >= 15)) || fail "space does not see that the prune freed room"
echo "OK: the prune deletes what was forgotten in both, and space sees it"

say "the offsite space on a real S3, like R2: the bucket's objects, page by page"
docker run -d --name "$NET-s3" --network "$NET" --network-alias s3 rclone/rclone:1.71 \
  serve s3 --addr :9000 --auth-key test-key,test-secret /data >/dev/null
S3=(-e OFFSITE_REPOSITORY=s3:http://s3:9000/arga-e2e/copias
  -e AWS_ACCESS_KEY_ID=test-key -e AWS_SECRET_ACCESS_KEY=test-secret)
for _ in $(seq 1 30); do
  "${BACKUP[@]}" "${S3[@]}" --entrypoint sh "arga-backup:$TAG" -c 'curl -s -o /dev/null http://s3:9000' && break
  sleep 1
done
"${BACKUP[@]}" "${S3[@]}" "arga-backup:$TAG" once
stored=$(docker exec "$NET-s3" sh -c 'find /data/arga-e2e/copias -type f -exec stat -c %s {} + | awk "{s += \$1} END {print s}"')
echo "in the bucket: $stored bytes"
at() {
  "${BACKUP[@]}" "${S3[@]}" -e OFFSITE_ALERT_PERCENT=100 -e "OFFSITE_QUOTA_BYTES=$1" "${@:2}" \
    "arga-backup:$TAG" space 2>&1
}
for page in 1000 3; do
  exact=$(at "$stored" -e "OFFSITE_LIST_PAGE=$page")
  short=$(at "$((stored - 1))" -e "OFFSITE_LIST_PAGE=$page")
  echo "$page at a time: $exact"
  ! grep -q WARNING <<<"$exact" || fail "$page at a time it measures more than what is in the bucket"
  grep -q WARNING <<<"$short" || fail "$page at a time it measures less than what is in the bucket"
done
echo "OK: it measures what is in the bucket, with and without pages"

say "offsite space: below the threshold it does not warn; above, it warns"
docker run --rm -v "$NET-backups:/backups" --entrypoint sh "arga-backup:$TAG" -c \
  'printf "TELEGRAM_BOT_TOKEN=test\nTELEGRAM_CHAT_ID=1\n" > /backups/notify-space.env'
below=$("${BACKUP[@]}" -e NOTIFY_ENV_FILE=/backups/notify-space.env "arga-backup:$TAG" space 2>&1)
echo "$below"
grep -q 'offsite uses .* of 10.00 GB (0 %)' <<<"$below" || fail "it did not say the offsite size"
! grep -q -e WARNING -e 'Telegram notification' <<<"$below" || fail "it warned below the threshold"
above=$("${BACKUP[@]}" -e NOTIFY_ENV_FILE=/backups/notify-space.env -e OFFSITE_QUOTA_BYTES=50000 \
  "arga-backup:$TAG" space 2>&1)
echo "$above"
grep -q 'WARNING: offsite uses .* above 75 %' <<<"$above" || fail "it did not see it is over the threshold"
grep -q 'Telegram notification did not go out' <<<"$above" || fail "it did not try to notify"
"${BACKUP[@]}" "arga-backup:$TAG" status | grep 'offsite uses' || fail "status does not say the offsite size"
echo "OK: it measures, stays quiet below and warns above"

say "retention: hourly backups for two days, daily for 70"
"${BACKUP[@]}" --entrypoint bash "arga-backup:$TAG" -c '
  set -euo pipefail
  mkdir -p /backups/work/dump && echo sintetico > /backups/work/dump/meta.env
  now=$(date -u +%s)
  for h in $(seq 1 48); do times+=($((now - h * 3600))); done
  for d in $(seq 3 70); do times+=($((now - d * 86400))); done
  for t in "${times[@]}"; do
    restic --quiet -r /backups/restic backup --host arga --time "$(date -u -d @$t "+%F %T")" /backups/work/dump
  done
  rm -rf /backups/work/dump
  echo "before: $(restic -r /backups/restic snapshots --host arga --json | grep -o "\"short_id\"" | wc -l) backups"
'
"${BACKUP[@]}" -e OFFSITE_REPOSITORY= --entrypoint bash "arga-backup:$TAG" -c '
  set -euo pipefail
  restic --quiet -r /backups/restic forget --host arga --keep-hourly 24 --keep-daily 7 --keep-weekly 5 --keep-monthly unlimited >/dev/null
  restic -r /backups/restic snapshots --host arga --json > /tmp/s.json
  total=$(grep -o "\"short_id\"" /tmp/s.json | wc -l)
  oldest=$(grep -o "\"time\":\"[^\"]*\"" /tmp/s.json | sort | sed -n 1p)
  echo "after: $total backups; the oldest $oldest"
  (( total >= 30 && total <= 40 )) || { echo "FAIL: the retention left $total"; exit 1; }
  old=$(date -u -d @$(( $(date -u +%s) - 60 * 86400 )) +%F)
  [[ ${oldest:8:10} < $old ]] || { echo "FAIL: the monthly one from two months ago is gone"; exit 1; }
'
"${BACKUP[@]}" "arga-backup:$TAG" verify

say "breaking the offsite repository data files on purpose"
"${BACKUP[@]}" --entrypoint sh "arga-backup:$TAG" -c '
  for pack in $(find /backups/offsite/data -type f); do
    chmod u+w "$pack"
    printf "basura" | dd of="$pack" bs=1 seek=100 conv=notrunc 2>/dev/null
  done
  echo "rotos: $(find /backups/offsite/data -type f | wc -l)"
'
if "${BACKUP[@]}" -e CHECK_OFFSITE_SUBSET=1/1 "arga-backup:$TAG" check; then
  fail "check did not see the broken file"
fi
echo "OK: check lo ha visto"
if "${BACKUP[@]}" "arga-backup:$TAG" verify; then
  fail "the test restore accepted a broken backup"
fi
echo "OK: the test restore does not accept it"
"${BACKUP[@]}" -e OFFSITE_REPOSITORY= "arga-backup:$TAG" verify
echo "OK: the local repository still restores"

say "the service: it starts, makes its backup and beats"
docker run -d --name "$NET-serve" "${CAPS[@]}" --network "$NET" -v "$NET-backups:/backups" \
  -e PGDATABASE=$DB -e PGPASSWORD=$BACKUP_PASSWORD -e RESTIC_PASSWORD=$RESTIC_PASSWORD \
  -e STARTUP_DELAY=1 "arga-backup:$TAG" >/dev/null
for _ in $(seq 1 60); do
  docker logs "$NET-serve" 2>&1 | grep 'local backup done' >/dev/null && break
  sleep 1
done
docker logs "$NET-serve" 2>&1 | sed 's/^/  | /'
docker logs "$NET-serve" 2>&1 | grep 'local backup done' >/dev/null || fail "the service did not make its backup"
docker exec "$NET-serve" find /backups/state/heartbeat -mmin -1 | grep . >/dev/null || fail "the service does not beat"

say "if the backup fails, it notifies once and the service goes on"
docker run --rm -v "$NET-backups:/backups" --entrypoint sh "arga-backup:$TAG" -c \
  'printf "TELEGRAM_BOT_TOKEN=test\nTELEGRAM_CHAT_ID=1\n" > /backups/notify.env'
docker run -d --name "$NET-broken" "${CAPS[@]}" --network "$NET" -v "$NET-backups:/backups" \
  -e PGDATABASE=$DB -e PGPASSWORD=not-the-right-one -e RESTIC_PASSWORD=$RESTIC_PASSWORD \
  -e STATE_DIR=/backups/state-broken -e NOTIFY_ENV_FILE=/backups/notify.env \
  -e STARTUP_DELAY=1 "arga-backup:$TAG" >/dev/null
for _ in $(seq 1 60); do
  docker logs "$NET-broken" 2>&1 | grep 'Telegram notification did not go out' >/dev/null && break
  sleep 1
done
docker logs "$NET-broken" 2>&1 | sed 's/^/  | /'
docker logs "$NET-broken" 2>&1 | grep 'Telegram notification did not go out' >/dev/null || fail "it did not try to notify"
[[ $(docker inspect -f '{{.State.Status}}' "$NET-broken") == running ]] || fail "the service went down"
docker exec "$NET-broken" test -f /backups/state-broken/failing-once || fail "it did not record the failure"
echo "OK: it tried to notify, recorded the failure and is still up"

say "all in order"
