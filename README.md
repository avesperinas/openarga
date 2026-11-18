# OpenArga

A self-hosted personal operating system. One place for your training, health, food, money,
calendar, trips, books, notes and plans, where every app is a module on a small kernel, your data
stays in your own Postgres, and your AI can read and act on it only through tools you allow.

> **Status: v0.1 in progress.** The code comes from a private system that has been in daily use
> for months; this repository is its open edition, being generalised for anyone to run. See
> `ROADMAP.md` and `TASKS.md`.

## What is inside

| App | What it does |
|---|---|
| Training | Strength training, one tap per set, and what the history says |
| Health | Steps, sleep, heart, weight and lab results (Apple Health, Google Health) |
| Nutrition | What you eat and drink, with its macros and micros |
| Recipes | Your home cookbook, with the nutrition worked out |
| Shopping | The shopping list that remembers what you buy |
| Finance | Accounts, investments, shared expenses and what everything is worth |
| Goals | Goals, habits and tasks |
| Calendar | Your events, holidays, sports fixtures and any iCal |
| Outings | What is on near you, read from your city's event pages, and what you want to do |
| Travel | Trip ideas, plans and the trips you made |
| Books | The books you read and want to read |
| Notes | Your notes, linked, with a Git backup |
| Study | Courses, classes, exams and grades |
| Insights | What your data says, every day and every week |
| Connections | Everything that comes from outside, in one place |

Every app has standard names in English and Spanish, and you can rename them in Settings.

## How it is built

```
            shell (Next.js PWA) · one app per module (React + Vite)
                                  │
                     gateway (login, routing, identity)
          ┌───────────────┬───────┴────────┬──────────────────┐
        kernel        module APIs       MCP server        connections hub
          └───────────────┴───────┬────────┴──────────────────┘
          Postgres: kernel.* + one schema and one role per module, RLS per person
```

- **The kernel rules.** Modules never call each other; they ask the kernel, which checks the
  manifest.
- **Isolation is enforced by Postgres**, not by the code: one role per module, row-level security
  per person, shared spaces for the rows you share.
- **The AI only acts through tools.** About three hundred MCP tools, each with its scope. The
  model never sees the schema or writes SQL. Any MCP client works.
- **Permission = OAuth scope = Postgres role**, the same chain for the UI, the API and the AI.
- **Every migration is backward compatible**, so a rollback always has somewhere to land.

The full set of principles is in `docs/adr/0001-principles.md`; the architecture in
`docs/platform/architecture.md`; how to write your own app in `docs/platform/module-contract.md`.

## Run it

Requirements: Docker with Compose, about 4 GB of RAM for the whole stack, and a domain with HTTPS
if you want to reach it (or connect Claude) from outside your network.

```bash
git clone https://github.com/avesperinas/openarga && cd openarga
cp openarga.example.yaml openarga.yaml   # the instance: see Configuration
cp .env.example .env                     # every empty PASSWORD, SECRET and TOKEN needs a long random value
uv run python scripts/compose.py         # writes docker-compose.yml from openarga.yaml
docker compose up -d --build
```

Open `http://localhost:8000`, sign in with `OPENARGA_ADMIN_USERNAME` and `OPENARGA_ADMIN_PASSWORD`
from `.env`, and the first-run wizard asks for your language, region, time zone, currency, home
area and the apps you want to see.

`scripts/stack-check.sh` boots the same stack with throwaway secrets and checks that every service
answers `/healthz`. To fill a value in `.env`: `openssl rand -hex 24`.

## Configuration

`openarga.yaml` describes the instance. `scripts/compose.py` reads it with the module manifests and
regenerates `docker-compose.yml`; run it again after every change.

| Key | What it sets |
|---|---|
| `domain` | `localhost`, or the public host name; public URLs become `https://<domain>` |
| `modules.enabled`, `modules.disabled` | which apps run: `all` or a list, minus the disabled ones |
| `defaults` | locale, time zone, currency, country, region and home area for new people |
| `auth.providers` | `local` (username and password), `google`, `oidc` (any OpenID Connect provider) |
| `ai` | the platform's model: provider, base URL, the `fast` and `smart` models, a monthly token cap |
| `connections` | `live`, or `fake` to answer every outside source from fixtures |
| `demo` | a public demo: anyone signs in as the synthetic cast, and MCP is read-only |

Secrets never go in `openarga.yaml`. `.env` holds the database passwords (one per module), the
session and client secrets, the Keycloak admin password, the first admin, and the keys of Google,
your OIDC provider and your AI provider.

### The demo

With `demo: true` the sign-in page offers the cast of `demo/personas.yaml` (Alex and Sam, who share
a space). Once the stack is up (the apps create their tables when they boot), `scripts/demo.py`
fills the instance with their data. It needs `DATABASE_URL`, the owner's connection to the
database:

```bash
uv run python scripts/demo.py list    # who and which apps, nothing written
uv run python scripts/demo.py         # seed: the cast and every app's `demo.py`
uv run python scripts/demo.py day     # one more simulated day
uv run python scripts/demo.py reset   # wipe the apps' data and seed again (demo instances only)
```

## AI

The AI does not use the apps; it uses tools. Every module declares its tools in its manifest with a
scope, and the MCP server at `https://<domain>/mcp` exposes them with OAuth 2.1: add it as a custom
connector in Claude (Settings shows what to paste) or point any MCP client at it. Each call runs as
the Postgres role its scope grants, so a read token cannot write even by mistake.

The platform calls a model itself only where a feature needs it (reading an events page with no
feed, writing the weekly insights), through one layer with narrow inputs and outputs. Anthropic,
OpenAI and any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM) work, and each person can bring
their own key. See `docs/platform/ai.md`.

## Connections

Everything that comes from outside goes through the Connections app (`modules/hub`): banks through
Enable Banking, Apple Health and Google Health, calendars and iCal, holidays, weather, books, films,
podcasts, maps and routes, prices and currencies, and more. One provider file per source, with its
schedule, its retries and credentials encrypted per person. What it brings lands in the kernel's
event log with a written contract, and the apps derive their own tables from it.

With `connections: fake` every provider that has a double answers from fixtures, which is how the
tests and the demo run without accounts anywhere.

## Security

- One Postgres role per module and row-level security per person: isolation is enforced by the
  database, and the tests run as the module role against a real Postgres.
- Login is Keycloak behind the gateway; modules never see a password or a token, only the identity
  the gateway injects.
- Permission is the same chain everywhere: OAuth scope, then Postgres role.
- Seeds and tests are synthetic: there is no personal data in the repository.

Report a vulnerability privately as `SECURITY.md` explains.

## Build your own app

```bash
scripts/new-module.sh garden Garden      # creates modules/custom/garden from the template
uv sync --all-packages
uv run pytest modules/custom/garden
uv run python scripts/compose.py         # the stack now runs it
```

A module is a manifest, a schema, a service on the module kit, its tools and widgets, and
optionally its own app. Forks keep their modules in `modules/custom/`, so updates from upstream
never touch them. `docs/platform/module-contract.md` is the contract and `modules/_template` the
living example.

## Contributing

`CONTRIBUTING.md` has the development loop and the rules a change has to follow; `AGENTS.md` is the
working agreement for humans and coding agents alike. Everyone taking part follows
`CODE_OF_CONDUCT.md`.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
