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
PG_PASSWORD=postgres-de-prueba
KERNEL_PASSWORD=kernel-de-prueba
BACKUP_PASSWORD=backup-de-prueba
RESTIC_PASSWORD=restic-de-prueba

cleanup() {
  [[ -n ${KEEP:-} ]] && return 0
  docker ps -aq --filter "network=$NET" | xargs -r docker rm -fv >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker volume rm "$NET-backups" >/dev/null 2>&1 || true
}
trap 'cleanup; [[ -n ${KEEP:-} ]] || docker rmi "arga-kernel:$TAG" "arga-backup:$TAG" >/dev/null 2>&1 || true' EXIT
cleanup

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FALLA: $*" >&2; exit 1; }

say "imágenes de este árbol"
"$ROOT/scripts/build-image.sh" kernel/Dockerfile "arga-kernel:$TAG"
"$ROOT/scripts/build-image.sh" backup/Dockerfile "arga-backup:$TAG"
docker network create --internal "$NET" >/dev/null
docker volume create "$NET-backups" >/dev/null

say "Postgres, el login de las copias y el esquema del kernel"
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

say "la copia no ve menos por la RLS y no puede escribir"
seen=$(docker run --rm --network "$NET" -e PGPASSWORD=$BACKUP_PASSWORD --entrypoint psql "arga-backup:$TAG" \
  -X -At -h postgres -U arga_backup -d $DB -c 'select count(*) from probe.readings')
[[ $seen == 5000 ]] || fail "arga_backup ve $seen filas de 5000"
refused=$(docker run --rm --network "$NET" -e PGPASSWORD=$BACKUP_PASSWORD --entrypoint psql "arga-backup:$TAG" \
  -X -At -h postgres -U arga_backup -d $DB -c 'delete from probe.readings' 2>&1 || true)
echo "$refused"
grep -q 'permission denied' <<<"$refused" || fail "arga_backup ha podido borrar"
echo "OK: ve las 5000 filas y un delete da permission denied"

say "una copia, a los dos repositorios"
"${BACKUP[@]}" "arga-backup:$TAG" once

say "restauración de prueba desde el de fuera"
"${BACKUP[@]}" "arga-backup:$TAG" verify

say "otra copia tras cambiar datos: deduplica y sigue restaurando la última"
psql -c "update probe.readings set note = 'cambiada' where id <= 10"
"${BACKUP[@]}" "arga-backup:$TAG" once
"${BACKUP[@]}" "arga-backup:$TAG" status
"${BACKUP[@]}" "arga-backup:$TAG" verify

say "si el de fuera está mal configurado, la copia local se hace igual"
latest() { "${BACKUP[@]}" --entrypoint sh "arga-backup:$TAG" -c 'restic -r /backups/restic snapshots latest --host arga --json | grep -o "\"time\":\"[^\"]*\""'; }
before=$(latest)
if "${BACKUP[@]}" -e OFFSITE_REPOSITORY=s3:https://r2.invalid "arga-backup:$TAG" once; then
  fail "once dio por buena una subida imposible"
fi
after=$(latest)
[[ $after != "$before" ]] || fail "sin la de fuera tampoco hubo copia local"
echo "OK: falla la subida y hay copia local nueva ($before -> $after)"

say "check de los dos repositorios"
"${BACKUP[@]}" "arga-backup:$TAG" check

say "la poda: lo que ya no usa ninguna copia se borra, aunque la copia de la hora ya la haya olvidado"
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
measured() { "${BACKUP[@]}" "arga-backup:$TAG" space 2>&1 | sed -n 's/.*fuera ocupa \([0-9]*\)\..* MB de.*/\1/p'; }
read -r local_before offsite_before <<<"$(sizes)"
space_before=$(measured)
echo "antes de la poda: local $local_before MB, fuera $offsite_before MB; space dice $space_before MB"
((space_before >= 20)) || fail "space no cuenta lo que espera a la poda ($space_before MB)"
"${BACKUP[@]}" "arga-backup:$TAG" daily
read -r local_after offsite_after <<<"$(sizes)"
space_after=$(measured)
echo "después: local $local_after MB, fuera $offsite_after MB; space dice $space_after MB"
((local_before - local_after >= 15)) || fail "la poda no ha borrado nada en el local"
((offsite_before - offsite_after >= 15)) || fail "la poda no ha borrado nada fuera"
((space_before - space_after >= 15)) || fail "space no ve que la poda ha liberado sitio"
echo "OK: la poda borra lo olvidado en los dos, y space lo ve"

say "el espacio de fuera en un S3 de verdad, como R2: los objetos del bucket, página a página"
docker run -d --name "$NET-s3" --network "$NET" --network-alias s3 rclone/rclone:1.71 \
  serve s3 --addr :9000 --auth-key clave-de-prueba,secreto-de-prueba /data >/dev/null
S3=(-e OFFSITE_REPOSITORY=s3:http://s3:9000/arga-e2e/copias
  -e AWS_ACCESS_KEY_ID=clave-de-prueba -e AWS_SECRET_ACCESS_KEY=secreto-de-prueba)
for _ in $(seq 1 30); do
  "${BACKUP[@]}" "${S3[@]}" --entrypoint sh "arga-backup:$TAG" -c 'curl -s -o /dev/null http://s3:9000' && break
  sleep 1
done
"${BACKUP[@]}" "${S3[@]}" "arga-backup:$TAG" once
stored=$(docker exec "$NET-s3" sh -c 'find /data/arga-e2e/copias -type f -exec stat -c %s {} + | awk "{s += \$1} END {print s}"')
echo "en el bucket: $stored bytes"
at() {
  "${BACKUP[@]}" "${S3[@]}" -e OFFSITE_ALERT_PERCENT=100 -e "OFFSITE_QUOTA_BYTES=$1" "${@:2}" \
    "arga-backup:$TAG" space 2>&1
}
for page in 1000 3; do
  exact=$(at "$stored" -e "OFFSITE_LIST_PAGE=$page")
  short=$(at "$((stored - 1))" -e "OFFSITE_LIST_PAGE=$page")
  echo "de $page en $page: $exact"
  ! grep -q AVISO <<<"$exact" || fail "de $page en $page mide más de lo que hay en el bucket"
  grep -q AVISO <<<"$short" || fail "de $page en $page mide menos de lo que hay en el bucket"
done
echo "OK: mide lo que hay en el bucket, con y sin páginas"

say "espacio de fuera: por debajo del umbral no avisa; por encima, avisa"
docker run --rm -v "$NET-backups:/backups" --entrypoint sh "arga-backup:$TAG" -c \
  'printf "TELEGRAM_BOT_TOKEN=de-prueba\nTELEGRAM_CHAT_ID=1\n" > /backups/notify-space.env'
below=$("${BACKUP[@]}" -e NOTIFY_ENV_FILE=/backups/notify-space.env "arga-backup:$TAG" space 2>&1)
echo "$below"
grep -q 'fuera ocupa .* de 10.00 GB (0 %)' <<<"$below" || fail "no dijo lo que ocupa fuera"
! grep -q -e AVISO -e 'aviso por Telegram' <<<"$below" || fail "avisó por debajo del umbral"
above=$("${BACKUP[@]}" -e NOTIFY_ENV_FILE=/backups/notify-space.env -e OFFSITE_QUOTA_BYTES=50000 \
  "arga-backup:$TAG" space 2>&1)
echo "$above"
grep -q 'AVISO: fuera ocupa .* por encima del 75 %' <<<"$above" || fail "no vio que pasa del umbral"
grep -q 'aviso por Telegram no salió' <<<"$above" || fail "no intentó avisar"
"${BACKUP[@]}" "arga-backup:$TAG" status | grep 'fuera ocupa' || fail "status no dice lo que ocupa fuera"
echo "OK: mide, calla por debajo y avisa por encima"

say "retención: copias cada hora durante dos días, cada día durante 70"
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
  echo "antes: $(restic -r /backups/restic snapshots --host arga --json | grep -o "\"short_id\"" | wc -l) copias"
'
"${BACKUP[@]}" -e OFFSITE_REPOSITORY= --entrypoint bash "arga-backup:$TAG" -c '
  set -euo pipefail
  restic --quiet -r /backups/restic forget --host arga --keep-hourly 24 --keep-daily 7 --keep-weekly 5 --keep-monthly unlimited >/dev/null
  restic -r /backups/restic snapshots --host arga --json > /tmp/s.json
  total=$(grep -o "\"short_id\"" /tmp/s.json | wc -l)
  oldest=$(grep -o "\"time\":\"[^\"]*\"" /tmp/s.json | sort | sed -n 1p)
  echo "después: $total copias; la más vieja $oldest"
  (( total >= 30 && total <= 40 )) || { echo "FALLA: la retención dejó $total"; exit 1; }
  old=$(date -u -d @$(( $(date -u +%s) - 60 * 86400 )) +%F)
  [[ ${oldest:8:10} < $old ]] || { echo "FALLA: no queda la mensual de hace dos meses"; exit 1; }
'
"${BACKUP[@]}" "arga-backup:$TAG" verify

say "rompo a posta los ficheros de datos del repositorio de fuera"
"${BACKUP[@]}" --entrypoint sh "arga-backup:$TAG" -c '
  for pack in $(find /backups/offsite/data -type f); do
    chmod u+w "$pack"
    printf "basura" | dd of="$pack" bs=1 seek=100 conv=notrunc 2>/dev/null
  done
  echo "rotos: $(find /backups/offsite/data -type f | wc -l)"
'
if "${BACKUP[@]}" -e CHECK_OFFSITE_SUBSET=1/1 "arga-backup:$TAG" check; then
  fail "check no ha visto el fichero roto"
fi
echo "OK: check lo ha visto"
if "${BACKUP[@]}" "arga-backup:$TAG" verify; then
  fail "la restauración de prueba ha dado por buena una copia rota"
fi
echo "OK: la restauración de prueba no la da por buena"
"${BACKUP[@]}" -e OFFSITE_REPOSITORY= "arga-backup:$TAG" verify
echo "OK: el repositorio local sigue restaurando"

say "el servicio: arranca, hace su copia y late"
docker run -d --name "$NET-serve" "${CAPS[@]}" --network "$NET" -v "$NET-backups:/backups" \
  -e PGDATABASE=$DB -e PGPASSWORD=$BACKUP_PASSWORD -e RESTIC_PASSWORD=$RESTIC_PASSWORD \
  -e STARTUP_DELAY=1 "arga-backup:$TAG" >/dev/null
for _ in $(seq 1 60); do
  docker logs "$NET-serve" 2>&1 | grep 'copia local hecha' >/dev/null && break
  sleep 1
done
docker logs "$NET-serve" 2>&1 | sed 's/^/  | /'
docker logs "$NET-serve" 2>&1 | grep 'copia local hecha' >/dev/null || fail "el servicio no hizo su copia"
docker exec "$NET-serve" find /backups/state/heartbeat -mmin -1 | grep . >/dev/null || fail "el servicio no late"

say "si la copia falla, avisa una vez y el servicio sigue"
docker run --rm -v "$NET-backups:/backups" --entrypoint sh "arga-backup:$TAG" -c \
  'printf "TELEGRAM_BOT_TOKEN=de-prueba\nTELEGRAM_CHAT_ID=1\n" > /backups/notify.env'
docker run -d --name "$NET-broken" "${CAPS[@]}" --network "$NET" -v "$NET-backups:/backups" \
  -e PGDATABASE=$DB -e PGPASSWORD=no-es-la-buena -e RESTIC_PASSWORD=$RESTIC_PASSWORD \
  -e STATE_DIR=/backups/state-broken -e NOTIFY_ENV_FILE=/backups/notify.env \
  -e STARTUP_DELAY=1 "arga-backup:$TAG" >/dev/null
for _ in $(seq 1 60); do
  docker logs "$NET-broken" 2>&1 | grep 'aviso por Telegram no salió' >/dev/null && break
  sleep 1
done
docker logs "$NET-broken" 2>&1 | sed 's/^/  | /'
docker logs "$NET-broken" 2>&1 | grep 'aviso por Telegram no salió' >/dev/null || fail "no intentó avisar"
[[ $(docker inspect -f '{{.State.Status}}' "$NET-broken") == running ]] || fail "el servicio se cayó"
docker exec "$NET-broken" test -f /backups/state-broken/failing-once || fail "no apuntó el fallo"
echo "OK: intentó avisar, apuntó el fallo y sigue en pie"

say "todo en orden"
