#!/usr/bin/env bash
set -euo pipefail

SERVER=${ARGA_SERVER:-server}
CONTAINER=${ARGA_PG_CONTAINER:-arga-postgres-1}
IMAGE=postgres:16-alpine
ROOT=/srv/backups/arga

usage() {
  echo "uso: $0 dump|verify <etiqueta> | rehearse <etiqueta> <imagen del kernel>" >&2
  exit 2
}

[[ $# -eq 2 || ( $# -eq 3 && $1 == rehearse ) ]] || usage
command=$1
label=$2
rehearsal_image=${3:-}
[[ $label =~ ^[a-z0-9][a-z0-9-]{0,62}$ ]] || { echo "etiqueta inválida: $label" >&2; exit 2; }
dir="$ROOT/$label"

FINGERPRINT_SQL=$(cat "$(dirname "${BASH_SOURCE[0]}")/../backup/fingerprint.sql")

remote() {
  ssh "$SERVER" "$@"
}

summarize() {
  awk -F '\t' '
    $2 == "sequence" { split($1, p, "."); seqs[p[1]]++; next }
    { split($1, p, "."); tables[p[1]]++; rows[p[1]] += $2; total += $2; count++ }
    END {
      printf "  %-10s %7s %9s %11s\n", "schema", "tablas", "filas", "secuencias"
      for (s in tables) printf "  %-10s %7d %9d %11d\n", s, tables[s], rows[s], seqs[s] | "sort"
      close("sort")
      printf "  %-10s %7d %9d\n", "total", count, total
    }'
}

dump() {
  if remote "sudo test -e '$dir'"; then
    echo "ya existe $dir: una etiqueta no se sobrescribe" >&2
    exit 1
  fi

  local started=$SECONDS
  local work
  work=$(remote "sudo docker exec -i $CONTAINER sh -s" <<EOF
set -eu
W=\$(mktemp -d)
cat > "\$W/fingerprint.sql" <<'SQL'
$FINGERPRINT_SQL
SQL
mkfifo "\$W/in"
psql -X -q -At -F '	' -v ON_ERROR_STOP=1 -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" \
  < "\$W/in" > "\$W/session.out" 2> "\$W/session.err" &
session=\$!
exec 3> "\$W/in"
printf '%s\n' "begin isolation level repeatable read, read only;" "select pg_export_snapshot();" >&3
tries=0
until [ -s "\$W/session.out" ]; do
  tries=\$((tries + 1)); [ \$tries -lt 300 ] || { cat "\$W/session.err" >&2; exit 1; }
  sleep 0.1
done
snapshot=\$(head -n 1 "\$W/session.out")
pg_dumpall -U "\$POSTGRES_USER" --globals-only > "\$W/globals.sql"
pg_dump -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" -Fc --snapshot="\$snapshot" -f "\$W/database.dump"
printf '%s\n' "\\\\o \$W/fingerprint.tsv" "\\\\i \$W/fingerprint.sql" "\\\\o" "commit;" >&3
exec 3>&-
wait \$session || { cat "\$W/session.err" >&2; exit 1; }
{
  echo "database=\$POSTGRES_DB"
  echo "bootstrap=\$(psql -X -At -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" -c 'select rolname from pg_roles where oid = 10')"
  echo "snapshot=\$snapshot"
  echo "server=\$(psql -X -At -U "\$POSTGRES_USER" -d "\$POSTGRES_DB" -c 'show server_version')"
  echo "taken_at=\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "\$W/meta.env"
rm "\$W/in" "\$W/session.out" "\$W/session.err" "\$W/fingerprint.sql"
echo "\$W"
EOF
)

  remote "sudo sh -c \"set -e
    install -d -m 700 -o root -g root '$ROOT' '$dir'
    docker cp '$CONTAINER:$work/.' '$dir/'
    docker exec '$CONTAINER' rm -rf '$work'
    grep -h '^IMAGE_TAG=' /srv/infra/stacks/arga/versions.env >> '$dir/meta.env'
    cd '$dir'
    sha256sum globals.sql database.dump fingerprint.tsv > SHA256SUMS
    chown -R root:root '$dir'
    chmod 600 '$dir'/*\""

  echo "dump '$label' en $SERVER:$dir ($((SECONDS - started)) s)"
  remote "sudo sh -c 'cd $dir && grep -v ^snapshot= meta.env && stat -c \"%s bytes  %n\" globals.sql database.dump'"
  remote "sudo cat '$dir/fingerprint.tsv'" | summarize
}

verify() {
  remote "sudo test -s '$dir/database.dump'" || { echo "no hay dump en $dir" >&2; exit 1; }
  remote "sudo sh -c 'cd $dir && sha256sum --quiet -c SHA256SUMS'" \
    || { echo "los ficheros de $dir no coinciden con su SHA256SUMS" >&2; exit 1; }

  local meta database bootstrap tag
  meta=$(remote "sudo cat '$dir/meta.env'")
  database=$(sed -n 's/^database=//p' <<<"$meta")
  bootstrap=$(sed -n 's/^bootstrap=//p' <<<"$meta")
  tag=$(sed -n 's/^IMAGE_TAG=//p' <<<"$meta")
  [[ $bootstrap =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "meta.env sin superusuario de arranque" >&2; exit 1; }
  [[ $tag =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "meta.env sin IMAGE_TAG" >&2; exit 1; }

  net="arga-restore-$label" pg="arga-restore-$label-pg" kernel="arga-restore-$label-kernel"
  cleanup() {
    remote "sudo docker rm -f '$pg' '$kernel' >/dev/null 2>&1; sudo docker network rm '$net' >/dev/null 2>&1; true"
  }
  cleanup
  trap cleanup EXIT
  remote "sudo docker network create --internal '$net' >/dev/null && sudo docker run -d --name '$pg' \
    --network '$net' --network-alias postgres -e POSTGRES_USER='$bootstrap' -e POSTGRES_DB=postgres \
    -e POSTGRES_PASSWORD=\$(head -c 24 /dev/urandom | base64) $IMAGE >/dev/null"

  local tries=0
  until remote "sudo docker logs '$pg' 2>&1 | grep -q 'init process complete' \
      && sudo docker exec '$pg' pg_isready -U '$bootstrap' -q"; do
    tries=$((tries + 1))
    [[ $tries -lt 60 ]] || { echo "el Postgres desechable no arrancó" >&2; exit 1; }
    remote "sleep 1"
  done

  local started=$SECONDS
  remote "sudo docker cp '$dir/.' '$pg:/restore/'"
  remote "sudo docker exec '$pg' sh -c '
    set -eu
    grep -vx \"CREATE ROLE $bootstrap;\" /restore/globals.sql > /tmp/globals.sql
    psql -X -q -v ON_ERROR_STOP=1 -U $bootstrap -d postgres -f /tmp/globals.sql
    pg_restore -U $bootstrap -d postgres --create --exit-on-error /restore/database.dump
  '"
  local restore_seconds=$((SECONDS - started))

  remote "sudo docker exec -i '$pg' sh -c 'cat > /tmp/fingerprint.sql'" <<<"$FINGERPRINT_SQL"
  local restored original
  restored=$(remote "sudo docker exec '$pg' psql -X -q -At -F '	' -v ON_ERROR_STOP=1 \
    -U '$bootstrap' -d '$database' -c 'begin isolation level repeatable read, read only' \
    -f /tmp/fingerprint.sql -c commit")
  original=$(remote "sudo cat '$dir/fingerprint.tsv'")

  echo "restaurado '$label' en un Postgres aislado ($restore_seconds s)"
  echo "origen:"
  summarize <<<"$original"
  echo "restaurado:"
  summarize <<<"$restored"

  local tables sequences
  tables=$(grep -vc $'\tsequence\t' <<<"$original" || true)
  sequences=$(grep -c $'\tsequence\t' <<<"$original" || true)
  if ! diff <(echo "$original") <(echo "$restored") >/dev/null; then
    echo "DISTINTO: estas entradas no coinciden (nombre, recuento o hash):" >&2
    diff <(echo "$original") <(echo "$restored") | grep '^[<>]' | cut -f1,2 >&2
    exit 1
  fi
  echo "OK: $tables tablas con el mismo recuento y el mismo hash, y $sequences secuencias en la misma posición"

  local kernel_image="${IMAGE_PREFIX:-ghcr.io/avesperinas/openarga}-kernel:$tag"
  if [[ -n $rehearsal_image ]]; then
    kernel_image="arga-kernel:ensayo-$label"
    echo "llevando $rehearsal_image al servidor como $kernel_image (no se despliega: solo se arranca aquí)"
    docker save "$rehearsal_image" | gzip -1 | remote "gunzip | sudo docker load -q >/dev/null && sudo docker tag $rehearsal_image $kernel_image"
    tag="$rehearsal_image"
  fi
  started=$SECONDS
  remote "sudo sh -c 'set -e
    env=\$(mktemp)
    trap \"rm -f \$env\" EXIT
    docker inspect -f \"{{range .Config.Env}}{{println .}}{{end}}\" arga-kernel-1 \
      | grep -E \"^(DATABASE_URL|MODULES_PATH)=\" > \$env
    echo APP_VERSION=$tag >> \$env
    docker run -d --name $kernel --network $net --env-file \$env $kernel_image >/dev/null'"
  local state=""
  for _ in $(seq 1 60); do
    state=$(remote "sudo docker inspect -f '{{.State.Status}} {{.State.Health.Status}}' '$kernel'")
    [[ $state == "running healthy" || $state == exited* ]] && break
    remote "sleep 2"
  done
  echo "kernel $tag contra la copia: $state ($((SECONDS - started)) s)"
  remote "sudo docker logs '$kernel' 2>&1 | grep -iv password | tail -n 8 | sed 's/^/  /'"
  [[ $state == "running healthy" ]] || { echo "el kernel no arrancó contra la copia restaurada" >&2; exit 1; }
  remote "sudo docker exec '$kernel' python -c '
import json, urllib.request as u
for path in (\"/healthz\", \"/readyz\", \"/modules\"):
    r = u.urlopen(\"http://127.0.0.1:8000\" + path, timeout=5)
    body = json.loads(r.read())
    if path == \"/modules\":
        body = sorted((m[\"id\"], m.get(\"enabled\")) for m in body)
    print(\" \", path, r.status, body)
'"
  echo "OK: la copia restaurada sirve"
  [[ -z $rehearsal_image ]] || rehearsal_report
}

rehearsal_report() {
  echo "ensayo: lo que dejó la migración"
  remote "sudo docker logs '$kernel' 2>&1 | grep -E 'dueño|migra|revisi' | sed 's/^/  kernel | /'" || true
  local after
  after=$(remote "sudo docker exec -i '$pg' psql -X -q -At -F '	' -U '$bootstrap' -d '$database'" <<'SQL'
select 'revision', version_num from alembic_version;
select format('%I.%I', n.nspname, c.relname),
       obj_description(c.oid, 'pg_class'),
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname), false, true, '')))[1]::text,
       (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I where user_id is null', n.nspname, c.relname), false, true, '')))[1]::text,
       (select a.attnotnull::text from pg_attribute a where a.attrelid = c.oid and a.attname = 'user_id')
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind = 'r' and obj_description(c.oid, 'pg_class') in ('arga:person', 'arga:catalog')
order by 1;
SQL
)
  local original
  original=$(remote "sudo cat '$dir/fingerprint.tsv'")
  printf '  %-40s %-13s %8s %8s %9s %s\n' tabla clase antes después sin-dueño obligatorio
  local problems=0
  while IFS=$'\t' read -r name class count orphans required; do
    [[ $name == revision ]] && { echo "  revisión: $class"; continue; }
    local before
    before=$(awk -F '\t' -v t="$name" '$1 == t { print $2 }' <<<"$original")
    local mark=""
    if [[ $class == arga:person && ( $orphans != 0 || $required != true ) ]]; then mark="  <-- FALLA"; problems=$((problems + 1)); fi
    if [[ -n $before && $before != "$count" ]]; then mark="$mark  <-- cambió el recuento"; problems=$((problems + 1)); fi
    printf '  %-40s %-13s %8s %8s %9s %s%s\n' "$name" "$class" "${before:--}" "$count" "$orphans" "$required" "$mark"
  done <<<"$after"
  [[ $problems -eq 0 ]] || { echo "ENSAYO FALLIDO: $problems problema(s)" >&2; exit 1; }
  echo "OK: ninguna fila de alguien sin dueño, dueño obligatorio, y ningún recuento cambiado"
  rehearsal_rls
}

rehearsal_rls() {
  local report
  report=$(remote "sudo docker exec -i '$pg' psql -X -q -At -F '	' -U '$bootstrap' -d '$database'" <<'SQL'
do $$
declare
    owner uuid;
    stranger uuid := '00000000-0000-4000-8000-0000000000ff';
    t record;
    total bigint; mine bigint; theirs bigint; nobody bigint;
begin
    if (select count(*) from kernel.users) <> 1 then
        raise notice 'sin una sola persona: no se comprueba la visibilidad';
        return;
    end if;
    select id into owner from kernel.users;
    create temp table if not exists rls_report (name text, role text, total bigint, mine bigint, theirs bigint, nobody bigint);
    grant all on rls_report to public;
    for t in
        select format('%I.%I', n.nspname, c.relname) as name, pg_get_userbyid(c.relowner) as role,
               c.relrowsecurity as rls
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where c.relkind = 'r' and obj_description(c.oid, 'pg_class') in ('arga:person', 'arga:catalog')
        union all
        select format('%I.events', n.nspname), 'mod_' || n.nspname, true
        from pg_namespace n
        where exists (select 1 from pg_roles r where r.rolname = 'mod_' || n.nspname)
          and exists (select 1 from pg_class v where v.relnamespace = n.oid and v.relname = 'events' and v.relkind = 'v')
        order by 1
    loop
        if not t.rls then continue; end if;
        -- Una vista de eventos es del kernel y filtra con la RLS de kernel.events: su total se cuenta
        -- en la tabla, porque contarla sin persona es, precisamente, no ver nada.
        if t.name like '%.events' and t.name <> 'kernel.events' then
            execute format('select count(*) from kernel.events where module = %L', split_part(t.name, '.', 1)) into total;
        else
            execute format('select count(*) from %s', t.name) into total;
        end if;
        execute format('set local role %I', t.role);
        perform set_config('arga.user_id', owner::text, true);
        execute format('select count(*) from %s', t.name) into mine;
        perform set_config('arga.user_id', stranger::text, true);
        execute format('select count(*) from %s', t.name) into theirs;
        perform set_config('arga.user_id', '', true);
        execute format('select count(*) from %s', t.name) into nobody;
        reset role;
        insert into rls_report values (t.name, t.role, total, mine, theirs, nobody);
    end loop;
end $$;
select * from rls_report order by name;
SQL
)
  [[ -n $report ]] || { echo "ensayo RLS: no hay nada que comprobar"; return 0; }
  echo "ensayo RLS: lo que ve el rol que consulta"
  printf '  %-40s %-16s %7s %9s %8s %7s\n' tabla rol total "la-dueña" "otra" nadie
  local problems=0
  while IFS=$'\t' read -r name role total mine theirs nobody; do
    local mark=""
    if [[ $mine != "$total" || $theirs != 0 || $nobody != 0 ]]; then
      mark="  <-- FALLA"
      problems=$((problems + 1))
    fi
    printf '  %-40s %-16s %7s %9s %8s %7s%s\n' "$name" "$role" "$total" "$mine" "$theirs" "$nobody" "$mark"
  done <<<"$report"
  [[ $problems -eq 0 ]] || { echo "ENSAYO RLS FALLIDO: $problems problema(s)" >&2; exit 1; }
  echo "OK: la persona ve todo lo suyo, otra persona no ve nada, y sin persona no se ve nada"
}

case $command in
  dump) dump ;;
  verify) verify ;;
  rehearse) verify ;;
  *) usage ;;
esac
