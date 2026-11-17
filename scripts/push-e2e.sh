#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
export RUN_ID=${RUN_ID:-$$}
NET=arga-two-services-$RUN_ID
P=two-$RUN_ID
TAG=${IMAGE_TAG:-two-services-$RUN_ID}

say() { printf '\n== %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

cleanup() {
  [[ -n ${KEEP:-} ]] && return 0
  docker ps -aq --filter "network=$NET" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

KEEP=1 "$ROOT/scripts/two-services.sh" kernel hub /catalogue

say "this tree's gateway, in front"
docker build -q -f "$ROOT/gateway/Dockerfile" -t "arga-gateway:$TAG" "$ROOT" >/dev/null
docker run -d --name "$P-gateway" --network "$NET" --network-alias gateway \
  -e KERNEL_URL=http://kernel:8000 -e APP_VERSION=v9.9.9 \
  -e OAUTH_ISSUER=https://arga.test/auth/realms/arga \
  -e OIDC_INTERNAL_URL=http://auth:8080/auth/realms/arga \
  -e OIDC_CLIENT_ID=arga-web -e OIDC_CLIENT_SECRET=relleno \
  -e PUBLIC_URL=https://arga.test -e SESSION_SECRET="$(openssl rand -hex 32)" \
  "arga-gateway:$TAG" >/dev/null
for _ in $(seq 1 30); do
  [[ $(docker inspect -f '{{.State.Health.Status}}' "$P-gateway") == healthy ]] && break
  sleep 2
done
[[ $(docker inspect -f '{{.State.Health.Status}}' "$P-gateway") == healthy ]] || {
  docker logs "$P-gateway" 2>&1 | tail -15; fail "the gateway never became healthy"; }
echo "  arga-gateway:$TAG sano"

say "Apple Health connected, and what it calls through the gateway"
docker run --rm --network "$NET" "arga-kernel:$TAG" python -c "
import httpx, sys
person = httpx.post('http://kernel:8000/internal/users', json={'subject': 'push-e2e-sintetico'}, timeout=30).json()['id']
created = httpx.post('http://hub:8000/connections', json={'provider': 'apple_health'},
                     headers={'x-arga-user': person}, timeout=30)
assert created.status_code == 201, created.text
token = created.json()['ingest_token']
url = 'http://gateway:8000/api/hub/push/apple-health'
body = [{'date': '2026-09-23', 'steps': 8412}, {'date': '2026-09-24', 'steps': 10310}]
auth = {'authorization': f'Bearer {token}'}

first = httpx.post(url, json=body, headers=auth, timeout=30)
print('  with token, two days:', first.status_code, first.json())
again = httpx.post(url, json=body, headers=auth, timeout=30)
print('  otra vez lo mismo:', again.status_code, again.json())
anonymous = httpx.post(url, json=body, timeout=30)
print('  sin token:', anonymous.status_code)
forged = httpx.post(url, json=body, headers={'authorization': 'Bearer ' + token[:-4] + 'xxxx', 'x-arga-user': person}, timeout=30)
print('  fake token with a person header:', forged.status_code)
listing = httpx.get('http://gateway:8000/api/hub/connections', headers=auth, timeout=30)
print('  the rest of /api/hub without a session:', listing.status_code)
creating = httpx.post('http://gateway:8000/api/hub/connections', json={'provider': 'apple_health'}, headers=auth, timeout=30)
print('  creating a connection without a session:', creating.status_code)

import datetime, time
figures = {'heart_rate_min': 48, 'heart_rate_avg': 72, 'heart_rate_max': 150, 'resting_heart_rate': 58,
           'walking_heart_rate': 95, 'hrv_ms': 40, 'vo2max': 44.1, 'active_kcal': 500, 'basal_kcal': 1700,
           'distance_km': 6.2, 'exercise_min': 30, 'stand_min': 180, 'stand_hours': 11, 'flights': 8,
           'sleep_min': 420, 'in_bed_min': 470, 'walking_speed_kmh': 5.1, 'step_length_cm': 72,
           'asymmetry_pct': 2.5, 'double_support_pct': 27, 'respiratory_rate': 14.5, 'environment_db': 62}
start = datetime.date(2024, 1, 1)
batch = [{'date': (start + datetime.timedelta(days=i)).isoformat(), 'steps': 6000 + i, **figures}
         for i in range(250)]
began = time.monotonic()
history = httpx.post(url, json=batch, headers=auth, timeout=300)
print('  250 days with everything:', history.status_code, history.json(), f'{time.monotonic() - began:.1f} s')
profile = httpx.post(url, json={'profile': {'blood_type': '0+', 'sex': 'female'}}, headers=auth, timeout=30)
print('  the profile:', profile.status_code, profile.json())
private = httpx.post(url, json=[{'date': '2026-09-24', 'sexual_activity': 1}], headers=auth, timeout=30)

moments, ends, values, sources = [], [], [], []
for day in range(7):
    for minute in range(400):
        begin = datetime.datetime(2025, 3, 1 + day, 6, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=1)))
        begin += datetime.timedelta(minutes=minute)
        for source, steps in (('Synthetic Apple Watch', 10), ('Synthetic iPhone', 9)):
            moments.append(begin.isoformat())
            ends.append((begin + datetime.timedelta(minutes=1)).isoformat())
            values.append(str(steps))
            sources.append(source)
samples = {'start': '\n'.join(moments), 'end': '\n'.join(ends), 'steps': '\n'.join(values),
           'source': '\n'.join(sources)}
began = time.monotonic()
week = httpx.post(url, json=samples, headers=auth, timeout=60)
print(f'  a week in {len(moments)} samples:', week.status_code, week.json(), f'{time.monotonic() - began:.1f} s')
print('  a key that is not on the list:', private.status_code)

ok = (first.status_code == 200 and first.json() == {'received': 2, 'new': 2}
      and history.status_code == 200 and history.json() == {'received': 500, 'new': 500}
      and profile.json() == {'received': 1, 'new': 1} and private.status_code == 422
      and week.json() == {'received': 6, 'new': 6}
      and again.json() == {'received': 2, 'new': 0}
      and anonymous.status_code == 401 and forged.status_code == 401
      and listing.status_code == 401 and creating.status_code == 401)
sys.exit(0 if ok else 1)
" || fail "the route does not behave as ADR-0071 and ADR-0074 say"

say "in the log, once per day and with its owner"
docker exec "$P-postgres" psql -U arga -d arga -tA -c "
  select e.payload->>'date', e.payload->>'steps', u.subject
  from kernel.events e join kernel.users u on u.id = e.user_id
  where e.type = 'health.steps' and e.payload->>'date' >= '2026-01-01' order by 1" | sed 's/^/  /'
count=$(docker exec "$P-postgres" psql -U arga -d arga -tA -c \
  "select count(*) from kernel.events where type = 'health.steps' and payload->>'date' >= '2026-01-01'")
[[ $count == 2 ]] || fail "expected 2 step events from 2026 and there are $count"
counts=$(docker exec "$P-postgres" psql -U arga -d arga -tA -c "
  select string_agg(type || '=' || n, ' ' order by type) from (
    select type, count(*) n from kernel.events where type like 'health.%' group by type) t")
echo "  $counts"
[[ $counts == "health.daily=250 health.profile=1 health.steps=258" ]] ||
  fail "expected 250 days with figures, one profile and 258 of steps"
week=$(docker exec "$P-postgres" psql -U arga -d arga -tA -c "
  select string_agg(distinct payload->>'steps', ',') from kernel.events
  where type = 'health.steps' and payload->>'date' between '2025-03-01' and '2025-03-07'")
echo "  the sample week, each day: $week"
[[ $week == 4000 ]] || fail "each day of the week had to be 4000 (the Watch's) and it is $week"

say "OK: the shortcut arrives through the gateway, with its token and only to its route"
