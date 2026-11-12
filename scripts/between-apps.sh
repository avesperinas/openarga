#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RUN_ID=${RUN_ID:-$$}
NET=arga-between-apps-$RUN_ID
P=between-$RUN_ID
TAG=${IMAGE_TAG:-between-apps-$RUN_ID}
PG_PASSWORD=postgres-de-prueba
KERNEL_PASSWORD=kernel-de-prueba
TOKEN=$(openssl rand -hex 32)
VERSION=v9.9.9
APPS=(shopping recipes vitals training planner study notebook arca macros goals carrera travel outings)

cleanup() {
  [[ -n ${KEEP:-} ]] && return 0
  docker ps -aq --filter "network=$NET" | xargs -r docker rm -fv >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap 'cleanup; [[ -n ${IMAGE_TAG:-} || -n ${KEEP:-} ]] || docker rmi "arga-kernel:$TAG" $(printf "arga-%s:$TAG " "${APPS[@]}") >/dev/null 2>&1 || true' EXIT
cleanup
"$ROOT/scripts/stale-ci.sh"

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FALLA: $*" >&2; exit 1; }

healthy() {
  local name=$1
  for _ in $(seq 1 60); do
    case $(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$name") in
      "running healthy") return 0 ;;
      exited*) break ;;
    esac
    sleep 2
  done
  docker logs "$name" 2>&1 | tail -15 | sed 's/^/  | /'
  fail "$name no llegó a estar sano"
}

HEALTH=(--health-cmd "python -c \"import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/readyz',timeout=5).status==200 else 1)\"" --health-interval 2s)

say "imágenes de este árbol"
if [[ -z ${IMAGE_TAG:-} ]]; then
  pids=()
  "$ROOT/scripts/build-image.sh" kernel/Dockerfile "arga-kernel:$TAG" & pids+=($!)
  for app in "${APPS[@]}"; do
    "$ROOT/scripts/build-image.sh" "modules/$app/Dockerfile" "arga-$app:$TAG" & pids+=($!)
  done
  for pid in "${pids[@]}"; do wait "$pid" || fail "no se construyó una imagen"; done
fi
echo "  kernel y ${APPS[*]}"

say "Postgres, los logins y el kernel"
docker network create "$NET" >/dev/null
docker run -d --name $P-postgres --network "$NET" --network-alias postgres \
  -e POSTGRES_USER=arga -e POSTGRES_PASSWORD=$PG_PASSWORD -e POSTGRES_DB=arga \
  --tmpfs /var/lib/postgresql/data \
  --health-cmd "pg_isready -U arga -h 127.0.0.1" --health-interval 1s postgres:16-alpine >/dev/null
healthy $P-postgres
passwords=(-e "KERNEL_DB_PASSWORD=$KERNEL_PASSWORD")
for app in "${APPS[@]}"; do passwords+=(-e "${app^^}_DB_PASSWORD=$app-de-prueba"); done
docker run --rm --network "$NET" -e ADMIN_DATABASE_URL=postgresql+asyncpg://arga:$PG_PASSWORD@postgres:5432/arga \
  "${passwords[@]}" "arga-kernel:$TAG" python -m kernel.roles | sed 's/^/  /'
docker run -d --name $P-kernel --network "$NET" --network-alias kernel \
  -e DATABASE_URL=postgresql+asyncpg://arga_kernel:$KERNEL_PASSWORD@postgres:5432/arga \
  -e MODULE_REGISTRATION_TOKEN="$TOKEN" -e APP_VERSION=$VERSION \
  "${HEALTH[@]}" "arga-kernel:$TAG" >/dev/null
healthy $P-kernel

run_app() {
  local app=$1 name=$2
  shift 2
  docker run -d --name "$name" --network "$NET" "$@" \
    -e DATABASE_URL=postgresql+asyncpg://svc_$app:$app-de-prueba@postgres:5432/arga \
    -e KERNEL_URL=http://kernel:8000 -e MODULE_REGISTRATION_TOKEN="$TOKEN" -e APP_VERSION=$VERSION \
    -e PUBLISH_INTERVAL_SECONDS=1 -e DERIVE_INTERVAL_SECONDS=1 \
    -e RECORDS_EVERY_SECONDS=2 -e MIRROR_EVERY_SECONDS=2 \
    -e PUBLISH_TICK_SECONDS=3600 \
    "arga-$app:$TAG" "${CMD[@]}" >/dev/null
}

say "las apps se registran, y los workers de quien publica"
for app in "${APPS[@]}"; do
  CMD=()
  run_app "$app" "$P-$app" --network-alias "$app" "${HEALTH[@]}"
done
for app in "${APPS[@]}"; do healthy "$P-$app"; done
for app in vitals training notebook macros carrera travel; do
  CMD=(python -m "$app.publisher")
  run_app "$app" "$P-$app-worker"
done
echo "  ${APPS[*]} sanas; Shopping y Arca publican desde su API; workers de vitals, training, notebook, macros, carrera y travel en marcha"

say "los cinco primeros caminos, como una persona sintética"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time
import httpx

person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
def until(what, check, seconds=60):
    for _ in range(seconds):
        found = check()
        if found:
            return found
        time.sleep(1)
    print(f'  no llegó: {what}'); sys.exit(1)

food = call('POST', 'http://recipes:8000/foods/manual', json={
    'name': 'Puerro', 'category_id': 'vegetable',
    'macros': {'kcal': 61, 'protein': 1.5, 'fat': 0.3, 'carbs': 14.15}})
recipe = call('POST', 'http://recipes:8000/recipes', json={
    'name': 'Porrusalda', 'servings': 4, 'tags': [],
    'ingredients': [{'food_id': food['id'], 'quantity': 400, 'unit': 'g'}]})
position = recipe['groups'][0]['ingredients'][0]['position']
added = call('POST', f\"http://recipes:8000/recipes/{recipe['id']}/shopping\",
             json={'servings': 2, 'positions': [position]})
listed = call('GET', 'http://shopping:8000/list')
items = {i['name']: i['quantity'] for g in listed['groups'] for i in g['items']}
print('  recipes → kernel → shopping:', added['added'], '· en la lista:', items)
assert items.get('Puerro') == '200 g', items

call('POST', 'http://vitals:8000/weight', json={'kg': 81.3})
weight = until('el peso en Training',
               lambda: call('GET', 'http://training:8000/today')['settings']['bodyweight'])
print('  vitals → log → training: peso', weight)
assert weight == 81.3, weight

item = next(i for g in listed['groups'] for i in g['items'])
call('PUT', f\"http://shopping:8000/list/items/{item['id']}/cart\", json={'in_cart': True})
call('POST', 'http://shopping:8000/list/finish')
def in_planner():
    layers = call('GET', 'http://planner:8000/calendars')
    apps = [l for l in layers if l['origin'] == 'app']
    if not apps:
        return None
    now = time.time()
    window = {'from': time.strftime('%Y-%m-%dT00:00:00+00:00', time.gmtime(now - 86400)),
              'to': time.strftime('%Y-%m-%dT00:00:00+00:00', time.gmtime(now + 2 * 86400))}
    found = [o for o in call('GET', 'http://planner:8000/occurrences', params=window) if o.get('href')]
    return (apps, found) if found else None
apps, found = until('la compra en Planner', in_planner)
print('  shopping → log → planner: capa', [(l['name'], l['app']) for l in apps],
      '·', [(o['title'], o['href']) for o in found])
assert apps[0]['app'] == 'shopping' and apps[0]['name'] == 'Shopping', apps
assert found[0]['href'] == '/shopping/historial', found

course = call('POST', 'http://study:8000/courses', json={'name': 'Alemán', 'tone': 3, 'subjects': []})
course_id = course['course']['id']
call('POST', 'http://notebook:8000/import', json={'notes': [
    {'folder': 'Study/Alemán/B1 Gramatik', 'title': 'DE 1.1 Kasus', 'content': 'Kasus.'}]})
written = call('POST', 'http://study:8000/notes', json={'course_id': course_id, 'title': 'Hoy', 'body': 'Dativ.'})
in_study = sorted(n['title'] for n in call('GET', 'http://study:8000/notes', params={'course_id': course_id}))
in_notebook = sorted(n['path'] for n in call('GET', 'http://notebook:8000/tree')['notes'])
print('  study ⇄ kernel ⇄ notebook: en el estudio', in_study, '· en Notebook', in_notebook)
assert in_study == ['DE 1.1 Kasus', 'Hoy'], in_study
assert 'Study/Alemán/Hoy' in in_notebook, in_notebook

made = call('POST', 'http://training:8000/exercises', json={
    'name': 'Press sintético', 'pattern': 'horizontal_push',
    'variant': {'name': 'Press sintético', 'implement': 'barbell'}})
variant = made['variants'][0]['id']
offered = until('el ejercicio en Notebook', lambda: [
    l for l in call('GET', 'http://notebook:8000/linkables') if l['id'] == variant])
note = call('POST', 'http://notebook:8000/notes', json={
    'title': 'Técnica', 'content': f\"Bajar la carga: [[{offered[0]['target']}|{offered[0]['title']}]]\"})
shown = until('la nota en Training', lambda: call(
    'GET', f'http://training:8000/stats/variants/{variant}?period=all')['notes'])
print('  training → log → notebook → log → training:', offered[0]['title'], '·', shown)
assert shown[0]['href'] == f\"/notebook/nota/{note['id']}\", shown

" || fail "las apps no comparten lo que deben"

say "el deporte hecho fuera: Arca → Training → Planner"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
since = str(datetime.now(ZoneInfo('Europe/Madrid')).date() - timedelta(days=3))
r = httpx.post('http://arca:8000/items', headers={'x-arga-user': person}, timeout=30, json={
    'category_id': 'activity', 'name': 'Natación', 'fields': {
        'sport': True, 'timetable': {'rule': 'FREQ=DAILY', 'start': '07:00', 'minutes': 45, 'since': since}}})
print('  arca: natación con horario desde', since, r.status_code)
assert r.status_code == 201, r.text
" || fail "Arca no guardó la natación"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
now = datetime.now(ZoneInfo('Europe/Madrid'))
today = now.date()
since = str(today - timedelta(days=3))
expected = 3 + (now.time() >= dtime(7, 45))
def until(what, check, seconds=90):
    for _ in range(seconds):
        found = check()
        if found:
            return found
        time.sleep(1)
    print(f'  no llegó: {what}'); sys.exit(1)
def swims_in_training():
    found = [a for a in httpx.get('http://training:8000/activities', headers=who, timeout=30,
                                  params={'since': since, 'until': '2100-01-01'}).json()
             if a['name'] == 'Natación']
    return found if len(found) >= expected else None
logged = until('la natación en Training', swims_in_training)
window = {'from': since + 'T00:00:00+00:00',
          'to': str(today + timedelta(days=1)) + 'T00:00:00+00:00'}
def swims_in_planner():
    httpx.get('http://planner:8000/calendars', headers=who, timeout=30)
    found = [o for o in httpx.get('http://planner:8000/occurrences', headers=who, params=window, timeout=30).json()
             if o['title'] == 'Natación']
    return found if sum(o['href'] == '/training/calendario' for o in found) >= expected else None
swims = until('la natación en Planner', swims_in_planner)
print('  arca → log → training → log → planner:', [(a['day'], a['start_time'], a['source']) for a in logged],
      '·', [(o['start'], o['href']) for o in swims])
assert len(logged) == expected and all(a['start_time'] == '07:00:00' and a['source'] == 'received' for a in logged), logged
done = [o for o in swims if o['href'] == '/training/calendario']
assert len(done) == expected, swims
days = [o['start'][:10] for o in swims]
assert len(days) == len(set(days)), swims
assert all(o['href'].startswith('/arca/') for o in swims if o not in done), swims
" || fail "el deporte de Arca no llegó a Training y a Planner"

say "lo que comes: Recipes → kernel → Macros → log → KPIs"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
food = call('POST', 'http://recipes:8000/foods/manual', json={
    'name': 'Pechuga sintética', 'category_id': 'protein',
    'macros': {'kcal': 120, 'protein': 23, 'fat': 2.5, 'carbs': 0}})
entry = call('POST', 'http://macros:8000/entries', json={
    'items': [{'food_id': food['id'], 'quantity': 200, 'unit': 'g'}]})
print('  recipes → kernel → macros:', entry['items'][0]['name'], entry['nutrients']['protein'], 'g de proteína')
assert entry['nutrients']['protein'] == 46, entry
for _ in range(60):
    found = [m for m in call('GET', 'http://goals:8000/metrics') if m['key'] == 'macros.protein']
    if found:
        break
    time.sleep(1)
else:
    print('  no llegó: la proteína a KPIs'); sys.exit(1)
print('  macros → log → kpis:', [(m['label'], m['last_value'], m['unit'], m['kind']) for m in found])
assert found[0]['last_value'] == 46 and found[0]['kind'] == 'amount', found
" || fail "lo apuntado en Macros no llegó a KPIs"

say "el peso, uno: Macros → kernel → Vitals → log → Macros y Training"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
def on(app, day):
    return {d['day']: d['kg'] for d in call('GET', f'http://{app}:8000/weight')['days']}.get(day)
def until(what, check, seconds=60):
    for _ in range(seconds):
        if check():
            return
        time.sleep(1)
    print(f'  no llegó: {what}'); sys.exit(1)
DAY = '2026-09-20'
logged = call('POST', 'http://macros:8000/weight', json={'kg': 79.4, 'day': DAY})
assert logged['latest'] is not None, logged
until('el peso de Macros a Macros y a Training', lambda: on('macros', DAY) == 79.4 and on('training', DAY) == 79.4)
print('  macros → kernel → vitals → log:', {app: on(app, DAY) for app in ('vitals', 'macros', 'training')})
assert on('vitals', DAY) == 79.4
again = call('POST', 'http://training:8000/weight', json={'kg': 79.0, 'day': DAY})
assert again['pending'] is False, again
until('la corrección desde Training', lambda: on('macros', DAY) == 79.0 and on('training', DAY) == 79.0)
entries = [e for e in call('GET', 'http://vitals:8000/weight')['entries'] if e['day'] == DAY]
print('  training corrige el mismo día:', {app: on(app, DAY) for app in ('vitals', 'macros', 'training')}, '· pesadas ese día en Vitals:', len(entries))
assert on('vitals', DAY) == 79.0 and len(entries) == 1, entries
" || fail "el peso no es el mismo en Vitals, Macros y Training"

say "lo que se custodia: Carrera → log → Arca, y sus notas en Notebook"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
job = call('POST', 'http://carrera:8000/employments', json={
    'company': 'Talleres Ejemplo S.L.', 'title': 'Analista de datos', 'started_on': '2024-03-01',
    'conditions': None})
for _ in range(60):
    kept = call('GET', 'http://arca:8000/custody')
    if kept:
        break
    time.sleep(1)
else:
    print('  no llegó: el contrato a Arca'); sys.exit(1)
print('  carrera → log → arca:', [(k['title'], k['category_id'], k['href'], k['active']) for k in kept])
assert kept[0]['href'] == f\"/carrera/empleo/{job['id']}\" and kept[0]['category_id'] == 'contract', kept
assert all('Talleres' not in i['name'] for i in call('GET', 'http://arca:8000/items'))
note = call('POST', f\"http://carrera:8000/employments/{job['id']}/notes\", json={'title': 'Proyectos'})
found = call('GET', 'http://carrera:8000/notes')
in_notebook = call('GET', f\"http://notebook:8000/notes/{note['id']}\")
print('  carrera → kernel → notebook:', note['folder'], '·', [n['title'] for n in found['by_employment'][job['id']]])
assert found['available'] and in_notebook['folder'] == note['folder'] == 'Carrera/Talleres Ejemplo S.L', (note, in_notebook)
" || fail "el contrato de Carrera no llegó a Arca, o sus notas no están en Notebook"

say "todo en Notebook: Carrera y Vitals → log → Notebook, sin nombrarse (ADR-0092)"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
def note(target):
    return call('GET', 'http://notebook:8000/notes/resolve', params={'target': target})['note']
def until(what, check, seconds=90):
    for _ in range(seconds):
        found = check()
        if found:
            return found
        time.sleep(1)
    print(f'  no llegó: {what}'); sys.exit(1)
ficha = until('el empleo de Carrera a Notebook', lambda: note('Carrera/Empleos/Talleres Ejemplo S.L.'))
full = call('GET', f\"http://notebook:8000/notes/{ficha['id']}\")
print('  carrera → log → notebook:', full['path'], '·', full['properties']['tipo'], '·', [a['name'] for a in full['arga']['apps']])
assert full['properties']['arga'].startswith('carrera:employment:') and '%% arga %%' in full['content'], full
day = until('el peso del día a su nota', lambda: note('2026-09-20'))
diary = call('GET', f\"http://notebook:8000/notes/{day['id']}\")
print('  vitals → log → notebook:', diary['path'], '· peso_kg =', diary['properties'].get('peso_kg'))
assert diary['properties'].get('peso_kg') == 79.0 and '### Vitals' in diary['content'], diary
refused = httpx.post('http://notebook:8000/tools/set_properties', headers={**who, 'x-arga-scopes': 'notebook:write'},
                     json={'note': full['id'], 'set': {'puesto': 'Otro'}}, timeout=30)
print('  set_properties sobre lo de Carrera:', refused.status_code)
assert refused.status_code == 422 and 'Carrera' in refused.json()['detail'], refused.text
" || fail "lo de Carrera y Vitals no llegó a Notebook, o se pudo cambiar allí"

say "un vuelo, en el calendario: Travel → log → Planner"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
from datetime import datetime, timedelta, timezone
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
day = (datetime.now(timezone.utc) + timedelta(days=10)).date()
trip = call('POST', 'http://travel:8000/trips', json={
    'title': 'Lisboa', 'starts_on': day.isoformat(), 'ends_on': (day + timedelta(days=3)).isoformat()})
madrid = call('POST', 'http://travel:8000/places', json={'name': 'Madrid', 'lat': 40.4168, 'lon': -3.7038})
lisbon = call('POST', 'http://travel:8000/places', json={'name': 'Lisboa', 'lat': 38.7223, 'lon': -9.1393})
call('POST', f\"http://travel:8000/trips/{trip['id']}/legs\", json={
    'from_place_id': madrid['id'], 'to_place_id': lisbon['id'], 'mode': 'plane',
    'travelled_on': day.isoformat(), 'departs_at': '07:15', 'arrives_at': '07:40',
    'carrier': 'Iberia', 'number': 'IB3102'})
window = {'from': f'{day}T00:00:00+00:00', 'to': f'{day + timedelta(days=1)}T00:00:00+00:00'}
def flight_in_planner():
    httpx.get('http://planner:8000/calendars', headers=who, timeout=30)
    found = [o for o in call('GET', 'http://planner:8000/occurrences', params=window)
             if o['title'].startswith('Vuelo')]
    return found or None
for _ in range(90):
    found = flight_in_planner()
    if found:
        break
    time.sleep(1)
else:
    print('  no llegó: el vuelo a Planner'); sys.exit(1)
flight = found[0]
start, end = datetime.fromisoformat(flight['start']), datetime.fromisoformat(flight['end'])
print('  travel → log → planner:', flight['title'], '·', flight['start'], '→', flight['end'], '·', flight['href'])
assert flight['title'] == 'Vuelo Iberia IB3102 · Madrid → Lisboa', flight
assert (end - start) == timedelta(minutes=85), flight
assert start.astimezone(timezone.utc).time() in (datetime(2000, 1, 1, 5, 15).time(), datetime(2000, 1, 1, 6, 15).time()), flight
assert flight['href'] == f\"/travel/viajes/{trip['id']}/dias/{day}\", flight
layers = {l['id']: l['name'] for l in call('GET', 'http://planner:8000/calendars') if l['origin'] == 'app'}
whole = [o for o in call('GET', 'http://planner:8000/occurrences', params=window) if o['title'] == 'Lisboa']
print('  capas:', layers[flight['calendar_id']], '·', [layers[o['calendar_id']] for o in whole])
assert layers[flight['calendar_id']] == 'Travel · Trayectos', layers
assert [layers[o['calendar_id']] for o in whole] == ['Travel'], whole
call('POST', f\"http://travel:8000/trips/{trip['id']}/blocks\", json={
    'title': 'Cena en el Chiado', 'kind': 'meal', 'day': day.isoformat(),
    'starts_at': '20:30', 'ends_at': '22:00'})
def dinner_in_planner():
    httpx.get('http://planner:8000/calendars', headers=who, timeout=30)
    found = [o for o in call('GET', 'http://planner:8000/occurrences', params=window)
             if o['title'] == 'Cena en el Chiado']
    return found or None
for _ in range(90):
    dinner = dinner_in_planner()
    if dinner:
        break
    time.sleep(1)
else:
    print('  no llegó: la cena a Planner'); sys.exit(1)
layers = {l['id']: l['name'] for l in call('GET', 'http://planner:8000/calendars') if l['origin'] == 'app'}
print('  travel → log → planner:', dinner[0]['title'], '·', dinner[0]['start'], '·', layers[dinner[0]['calendar_id']])
assert layers[dinner[0]['calendar_id']] == 'Travel · Plan', layers
assert datetime.fromisoformat(dinner[0]['end']) - datetime.fromisoformat(dinner[0]['start']) == timedelta(minutes=90)
" || fail "el vuelo o la cena de Travel no llegaron a Planner con su hora"

say "los viajes que se planean, en Ganas: Travel → log → Outings, y Outings → kernel → Travel"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import sys, time, httpx
from datetime import datetime, timedelta, timezone
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'between-apps-sintetico'}, timeout=30).json()['id']
who = {'x-arga-user': person}
def call(method, url, **kw):
    r = httpx.request(method, url, headers=who, timeout=30, **kw)
    if r.status_code >= 400:
        print(f'  {method} {url}: {r.status_code} {r.text}'); sys.exit(1)
    return r.json() if r.content else None
day = (datetime.now(timezone.utc) + timedelta(days=40)).date()
plan = call('POST', 'http://travel:8000/trips', json={
    'title': 'Budapest', 'starts_on': day.isoformat(), 'ends_on': (day + timedelta(days=3)).isoformat(),
    'status': 'plan'})
idea = call('POST', 'http://travel:8000/ideas', json={'title': 'Japón en sakura', 'months': [3, 4]})
def in_ganas():
    found = call('GET', 'http://outings:8000/planned')
    titles = {o['title']: o for o in found}
    return titles if {'Budapest', 'Japón en sakura'} <= set(titles) else None
for _ in range(90):
    ganas = in_ganas()
    if ganas:
        break
    time.sleep(1)
else:
    print('  no llegaron: los viajes a Ganas', call('GET', 'http://outings:8000/planned')); sys.exit(1)
print('  travel → log → outings:', [(o['title'], o['phase'], o['href']) for o in ganas.values()])
assert ganas['Budapest']['href'] == f\"/travel/viajes/{plan['id']}\", ganas
assert ganas['Japón en sakura']['phase'] == 'idea', ganas
wish = call('POST', 'http://outings:8000/wishes', json={
    'kind': 'trip', 'name': 'Escocia', 'place': {'name': 'Edimburgo', 'lat': 55.9533, 'lon': -3.1883}})
made = call('POST', f\"http://outings:8000/wishes/{wish['id']}/idea\")
ideas = [one['title'] for one in call('GET', 'http://travel:8000/ideas')]
print('  outings → kernel → travel:', made, ideas)
assert 'Escocia' in ideas and made['already'] is False, (made, ideas)
" || fail "los viajes de Travel no llegaron a Ganas, o la gana no pasó a idea"

say "sin el token, Shopping no apunta nada a nadie"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import httpx, sys
r = httpx.post('http://shopping:8000/capabilities/shopping.add', json={'items': [{'name': 'x'}]}, timeout=30)
print('  POST /capabilities/shopping.add sin token:', r.status_code)
sys.exit(0 if r.status_code == 401 else 1)
" || fail "Shopping aceptó una petición que no venía del kernel"

say "OK: las apps comparten por el kernel, entre contenedores de verdad"
