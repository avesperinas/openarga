# A public demo on a small machine

One script puts the demo on a small Ubuntu machine and publishes it through a Cloudflare Tunnel.
Nothing listens to the internet: the tunnel connects out, the gateway and Postgres bind `127.0.0.1`,
and the machine's firewall can stay with only SSH open.

```
visitor ── https ──> Cloudflare ──tunnel──> cloudflared ──> http://localhost:8000 (gateway)
                     (TLS ends here)        (on the machine)  shell, apps, MCP, sign-in
```

The demo is the synthetic cast of `demo/personas.yaml` (Alex and Sam). Connections answer from
fixtures (`connections: fake`), the AI layer has no provider, MCP is read-only, and nothing in it is a
real person's data.

## What you need

- A machine with Ubuntu 24.04, ARM64 or x86-64, and a user with `sudo`. Oracle Cloud's Always Free
  Ampere A1 instance (ARM64) is enough. Give it 4 cores and 12 GB or more: the stack is about 35
  containers, and the first build takes a while.
- A domain on Cloudflare, for example `openarga-demo.avesperinas.com`.
- A tunnel. In Cloudflare, Zero Trust, Networks, Tunnels: create one of type Cloudflared and copy its
  token. Then add a public hostname to it: your domain, service type `HTTP`, URL `localhost:8000`.
  Cloudflare creates the DNS record.

## Run it

```bash
git clone https://github.com/avesperinas/openarga.git ~/openarga
cd ~/openarga
TUNNEL_TOKEN=<the token> scripts/public-demo.sh openarga-demo.avesperinas.com
```

The token can also be the second argument, but the environment keeps it out of the process list.
`--dry-run` prints every step and changes nothing, so read that first:

```bash
scripts/public-demo.sh --dry-run openarga-demo.avesperinas.com
```

Run it again whenever you want: every step checks what is there. It updates the checkout, rebuilds
what changed, applies the new schema and keeps the secrets of the existing `.env`.

## What it does

1. Installs `ca-certificates`, `curl`, `git`, `gnupg`, `openssl` and `cron`, then Docker Engine and
   the compose plugin from Docker's own apt repository, then `uv`. Anything already there is left
   alone.
2. Clones or updates `~/openarga` (`OPENARGA_DIR`, `OPENARGA_REPO` and `OPENARGA_REF` change that).
3. Creates `openarga.yaml` from the example if it is missing and sets `domain`, `demo: true` and
   `connections: fake`. The AI provider stays `none`, and the script refuses to go on if it is not.
4. Generates `.env` with `scripts/stack-env.sh` only if it is missing (mode 600), and keeps
   `OPENARGA_DEMO=true`, `PUBLIC_URL`, `AUTH_ISSUER` and `MCP_PUBLIC_URL` pointing at
   `https://<domain>`.
5. Writes `docker-compose.override.yml` so the gateway and Postgres bind `127.0.0.1` only, then runs
   `scripts/compose.py` and `docker compose up -d --build --wait`.
6. Waits until every service reports healthy, then seeds the cast with `scripts/demo.py`, trying up
   to three times, since a fresh machine runs this step only once.
7. Installs the user's crontab block below.
8. Installs `cloudflared` from Cloudflare's apt repository and runs it as the `cloudflared` systemd
   service. The token goes into `/etc/cloudflared/tunnel.env` (root only, mode 600), and the unit
   reads it from there, so it is in no command line, no repository file and no log.
9. Checks `http://127.0.0.1:8000/healthz` and `https://<domain>/healthz`.

## A copy of the cast per visitor

With `DEMO_COPIES=true` (the default) every visitor gets an Alex and a Sam of their own, made in the
language chosen at the door, so nobody sees or undoes what another visitor does. Switching between
Alex and Sam stays in the same copy. `OPENARGA_DEMO_COPIES=true` in `.env` turns it on for the kernel
and the gateway, and `scripts/demo.py keep` looks after the copies:

- it keeps `OPENARGA_DEMO_POOL` ready copies per language (default 2), so the door answers at once;
- a copy goes when nobody has used it for `OPENARGA_DEMO_IDLE_MINUTES` (default 30) or
  `OPENARGA_DEMO_COPY_MINUTES` after it was handed out (default 120), and the visitor's session ends
  with it;
- never more than `OPENARGA_DEMO_COPIES_MAX` copies at once (default 20). When all are taken the door
  says so and tries again by itself;
- the workers only keep up the people someone used in the last 30 minutes.

Making a copy takes about ten seconds. While copies are on, `demo reset` refuses to run: it would
wipe every visitor's copy.

## The schedule

With copies:

```
every minute   public-demo.sh demo keep    drop the copies nobody uses, make ready ones
```

Without copies (`DEMO_COPIES=false`), everyone shares the cast:

```
0 8 (Madrid)   public-demo.sh demo day     a new simulated day
30 4 (Madrid)  public-demo.sh demo reset   wipe the apps' data and seed again
```

Times are Madrid time whatever the machine's time zone: Ubuntu's cron ignores `CRON_TZ`, so each line
runs every hour at its minute and goes on only when the hour in Madrid matches. The crontab calls the
script inside `~/openarga`, so an update of the checkout is what the next run uses. `DEMO_DAY_AT` and
`DEMO_RESET_AT` change them (`"minute hour"`). Output goes to `~/openarga-demo.log` (`DEMO_LOG`).
`public-demo.sh demo seed|day|reset|keep` runs the same command by hand, with the owner's connection to
Postgres on `127.0.0.1:5433`. `reset` only runs on a demo instance.

## Updating it

Run the script again without a token: it keeps the tunnel the machine already has, pulls `main`,
rebuilds what changed and restarts it, so the demo is only away for the seconds a container takes to
come back.

```bash
cd ~/openarga && scripts/public-demo.sh <domain>
```

## Behind a proxy that ends TLS

Visitors reach the stack over https, and the stack only ever sees http from `cloudflared`. This is
what holds, and it was checked against a local stack with a TLS-terminating proxy that adds
`X-Forwarded-Proto`, `X-Forwarded-For` and `X-Forwarded-Host`:

- **Redirects and links.** Every public URL comes from `PUBLIC_URL` (`https://<domain>`), not from the
  `Host` header, so redirects, the sign-in callback and the OAuth metadata are https.
- **Cookies.** The session cookie is `__Host-arga_session` with `Secure; HttpOnly; SameSite=Lax`.
  Keycloak's cookies are `Secure` too.
- **Keycloak.** It runs with `KC_PROXY_HEADERS=xforwarded` and `KC_HOSTNAME=https://<domain>/auth`.
  The issuer is `https://<domain>/auth/realms/arga` and every endpoint in its discovery document is
  https.
- **MCP.** `https://<domain>/mcp` answers 401 with `resource_metadata` pointing at
  `https://<domain>/.well-known/oauth-protected-resource/mcp`, which names the issuer above and only
  `:read` scopes in a demo. Claude connects with its pre-registered client (`claude`); the realm does
  not offer open dynamic client registration.
- **Changing the domain.** `auth-sync` updates the return addresses of the `arga-web` client when
  `PUBLIC_URL` changes, so running the script again with another domain does not leave the old one
  behind.

## Looking after it

```bash
cd ~/openarga
docker compose ps                      # every service healthy
docker compose logs -f gateway         # or any other service
systemctl status cloudflared           # the tunnel
tail -f ~/openarga-demo.log            # the daily day and the nightly reset
```

- **A new tunnel token:** run the script again with the new `TUNNEL_TOKEN`.
- **Update:** run the script again. `OPENARGA_REF` picks a branch or a tag.
- **Take it down:** `docker compose down`, `sudo systemctl disable --now cloudflared`, and remove the
  block between `# openarga public demo: begin` and `end` from `crontab -e`.
- **Disk:** images and volumes grow with updates; `docker image prune -f` frees the old ones.
