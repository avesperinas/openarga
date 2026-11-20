# Tasks: v0.1

Three phases. **Bootstrap** was done by one agent and is merged. **Parallel** is split between
Platform (P), Apps-1 (A1) and Apps-2 (A2), with the ownership rules of `AGENTS.md`. **Release**
comes after all three.

Status: `todo` · `doing` · `pr` · `done`. Update only your own lines.

## Phase 1 · Bootstrap · `done`

Export by allowlist from the original private project (without Carrera, Arca and Chuping, the
release pipeline, the deploy declarations and every Spanish doc), comments stripped, modules
renamed to standard ids, migrations squashed to one baseline per module, hostnames and accounts
moved to configuration, the realm URL resolved at deploy time, the six frozen interfaces with
stubs, the language guard and its baseline, CI on GitHub Actions, the base docs and the
foundational ADRs.

App ids: `training`, `vitals` (Health), `macros` (Nutrition), `recipes`, `shopping`, `money`
(Finance), `goals`, `outings`, `travel`, `library` (Books), `planner` (Calendar), `notebook`
(Notes), `insights`, `study`, `hub` (Connections). An id never matches an event category
(`finance`, `health`, `calendar`, `books`, `notes`...): if it did, the app could publish events as
if it were a connection.

---

## Phase 2 · Parallel

### Platform (P)

| Id | Task | Verify | Status |
|---|---|---|---|
| P1 | **Local login.** Keycloak realm with local users and a first admin created on boot; Google and generic OIDC optional by config. Realm and auth texts in English | Login e2e with a local user in CI | `doing` (realm, first admin and optional OIDC done and tested; the stack boots healthy on Docker. Open: the login e2e with a local user: `scripts/login-e2e.sh` predates the realm taking `PUBLIC_URL` and the first admin, and needs `PUBLIC_URL` on auth, `MCP_RESOURCE_URL` on the gateway and its realm check updated; with those it passes up to its last phase, where the local form does not show) |
| P2 | **Instance config and compose.** `openarga.yaml`: domain, enabled modules, default locale, time zone and currency, auth providers, AI defaults. `scripts/compose.py` generates `docker-compose.yml` (Postgres, Keycloak, gateway, shell, MCP, one service per enabled module) and the gateway routes from it and the manifests. A CI job boots the stack and checks every `/healthz` | Disable two modules, regenerate, the stack boots without them | `doing` (config, generator and module disabling done and tested. First Docker run found six faults, fixed in #181 to #184: `.env` names, `PUBLIC_URL` for auth, `HUB_CREDENTIALS_KEY`, money worker entry point, shell health check, `host.docker.internal` for the hub. The generated stack now boots with 35 healthy containers, every service reports the release (`APP_VERSION` from `OPENARGA_VERSION`, `0.1.0` by default) and the apps wait for the hub. Open: a `scripts/stack-check.sh` run) |
| P3 | **Person preferences.** Storage, API and Settings screen in the shell; the gateway sends `x-arga-locale`, `x-arga-timezone`, `x-arga-currency`, `x-arga-country`, `x-arga-region`, `x-arga-area`. Remove hardcoded `Europe/Madrid`, `es-ES` and `EUR` from kernel, gateway, shell and `packages/**` | The same data rendered in two locales and two time zones | `done` |
| P4 | **i18n of the platform.** Shell, `packages/**`, kernel, gateway, MCP and hub in en and es; Storybook stories in both languages. Empty the baseline for every Platform file | Their lines gone from `tests/spanish_baseline.txt` | `done` |
| P5 | **First-run wizard.** Language, country and region, time zone, currency, home area, apps to enable | Playwright from empty database to dashboard | `doing` (wizard built and unit-tested; needs Docker: Playwright from an empty database in `scripts/desktop-e2e.sh`) |
| P6 | **AI layer.** In `hub`: providers (Anthropic Messages, OpenAI-compatible), roles `fast` and `smart`, per-person key, budgets, attempt log, Settings screen. `ai.extract` with schema validation; `ai.run` agent loop with OpenArga MCP tools under the app's token, plus `web.search` (SearXNG or Brave) and `web.fetch`. The agenda reader moves to `ai.extract`. Remove the subscription runner (`claude_run`), the Claude account provider and its realm client | Contract tests per provider against recorded responses; `ai.run` end to end with the fake provider; budget cut | `done` |
| P7 | **Fake mode for every provider.** Deterministic fixtures for bank, health, calendars, weather, books, food, places, routes, photos, agendas | The demo boots with no network | `done` |
| P8 | **Hub clean-up.** Out: INE, Bitvavo, IMAP, the Spanish funds catalogue. Prices by ISIN or ticker from a configurable source. `institutions.toml` documented for contributors. Calendar subscription catalogue: any ESPN team, Formula 1, any iCal; holidays by country and region | Tests of the remaining providers | `done` |
| P9 | **Fork-friendly.** App icons, names, families and launcher read from manifests (today: `scripts/make-pwa.mjs`, `packages/ui/src/appearance.ts`, `shell/app/lib/panels.ts`, `kernel/src/kernel/desktop.py`); modules discovered also in `modules/custom/`; `new-module` produces a module that passes CI | Generate a module into `modules/custom/`, CI green with it | `done` |
| P10 | **Demo mode.** `scripts/demo.py` runs every module seed for the cast; daily simulated life; nightly reset; "Try the demo" login; MCP read-only in demo | Empty database to populated demo in one command, in CI | `doing` (seed, day, reset, demo login and read-only MCP done, and `scripts/demo.py` seed, day and reset run on a live stack; each person's own content is written in their language, what the two share is in English. Open: an image that runs the daily day and the nightly reset) |
| P11 | **Platform docs.** README with screenshots, install, configuration, architecture, AI, connections, security, build your own app; CONTRIBUTING, SECURITY, CODE_OF_CONDUCT | Every command in them run once | `doing` (every page written; README screenshots in `docs/screenshots/`; the commands that boot the stack were run on Docker. Open: the Ollama and OIDC steps on a real provider) |

Suggested order: P3, P4 (start), P6 and P1 first, because the apps consume them; then P2, P7, P8,
P9; then P5, P10, P11. Answer `needs-platform` issues before starting a new task.

### Apps-1 (A1): training, vitals, macros, recipes, shopping, money, goals

| Id | Task | Verify | Status |
|---|---|---|---|
| A1.1 | **English everywhere but the UI**, per module: tool descriptions, glossary, errors, logs, routes, identifiers, tests | Manifest validator; MCP list test | `done` |
| A1.2 | **UI in en and es**, per module: every string to `ui/src/i18n/{en,es}.json`, server texts (widgets, panel, notifications) to `src/<id>/i18n/` | Module files gone from the baseline | `done` |
| A1.3 | **Preferences**: no hardcoded time zone, locale or currency | Tests in two time zones and two currencies | `done` |
| A1.4 | **Finance simplified** (`money`): bank by API, CSV and OFX import, holdings snapshots, base currency, shared expenses kept; tax, fund certificates, crypto and mail inlets removed | Import a synthetic CSV; isolation tests | `done` |
| A1.5 | **Bilingual catalogues**: exercises (training), nutrients (macros), shopping sections, recipe categories | Parity test | `done` |
| A1.6 | **Demo seeds**: `demo.py` per module for Alex and Sam, coherent over 18 months | Seeds run twice without duplicates | `done` |
| A1.7 | **App docs** in `docs/apps/<id>.md` | Links resolve | `done` |

Suggested order: per module, A1.1 then A1.2 then A1.3; A1.4 when `money` is reached; A1.6 last.

### Apps-2 (A2): outings, travel, library, planner, notebook, insights, study

| Id | Task | Verify | Status |
|---|---|---|---|
| A2.1 | **English everywhere but the UI**, per module, as A1.1 | Manifest validator; MCP list test | `done` |
| A2.2 | **UI in en and es**, per module, as A1.2 | Module files gone from the baseline | `done` |
| A2.3 | **Preferences**, as A1.3 | Tests in two time zones | `done` |
| A2.4 | **Outings area profile**: `modules/outings/areas/*.yaml` (Pamplona and Munich) with core towns, region, sources, search templates, seasonal hints, geocoding suffix, prompt language. Zone becomes `near` and `region`. Map built from the profile's bounding box (move `scripts/make-area-map.mjs` into the module) | The same tests pass with both profiles | `done` |
| A2.5 | **Calendar settings** (`planner`): holidays by country and region plus local ones; subscription catalogue UI | Tests with two countries | `done` |
| A2.6 | **Insights and Outings on `ai.run`** instead of `claude.run` | End to end with the fake provider | `done` |
| A2.7 | **Demo seeds**, as A1.6 | Seeds run twice without duplicates | `done` |
| A2.8 | **App docs**, as A1.7 | Links resolve | `done` |

Suggested order: A2.4 and outings first (it is the most visible app), then the rest per module.

---

## Phase 3 · Release

| Id | Task | Status |
|---|---|---|
| R1 | Fresh clone, `make demo`, every app opened in both languages, AI layer with a real key and with Ollama, `tests/spanish_baseline.txt` empty | `doing` (first Docker run done, its faults fixed, see P2; second run: shared wishes and foods could not be updated by their publishers under RLS, fixed in #205 and #212, and the Ollama steps are in `docs/platform/ai.md`; the 503 for about 1 s after start, while `hub` registers, is closed: the other modules wait for `hub` healthy and its healthcheck runs every 2 s (what is left in the logs are answers on purpose: `ai.run` 503 when no AI provider is set, `notes.push` 404 when no GitHub repository is connected). Open: a fresh clone on the three commands of `docs/releases/v0.1.0.md`, the AI layer with a real key and with Ollama, and `tests/spanish_baseline.txt` empty, which it is) |
| R2 | Tag `v0.1.0`, public images, release notes, README screenshots | `doing` (release notes in `docs/releases/v0.1.0.md` and README screenshots done; the tag and the public images are left) |
| R3 | Public demo (where it is hosted is the owner's decision) | `todo` |
