# AGENTS.md

How agents (and humans) work on OpenArga. Read this, `ROADMAP.md` and `TASKS.md` before touching
anything.

## The principles

Twelve rules are the reason this project exists. They are in `docs/adr/0001-principles.md` and do
not change without a new ADR. The ones that bite every day:

- **Modules never call each other.** They ask the kernel, which checks the manifest.
- **One Postgres schema and one role per module.** No module has a grant on another's schema.
- **No colours, spacing, radii or fonts outside `packages/ui` tokens.** CI checks it.
- **The AI acts only through tools.** Platform model calls go through the AI layer
  (`ai.extract`, `ai.run`), with narrow input and output.
- **Permission = OAuth scope = Postgres role.** One chain for UI, API and AI.
- **Every migration is backward compatible.** Old code must boot against the new schema.
- **No query sees another person's rows, and Postgres guarantees it**, not the code: every table
  declares its class (`arga:person`, `arga:catalog`, `arga:shared`, `arga:system`) and has RLS.
- **Zero personal data.** Seeds and tests are synthetic.

## Three workstreams, disjoint ownership

During the v0.1 push three agents work in parallel. Each owns a set of paths and **never edits a
path it does not own**. If you need a change outside your paths, open a GitHub issue labelled
`needs-platform`, `needs-apps-1` or `needs-apps-2`, and keep going with a stub or a workaround
inside your own paths.

| Path | Owner |
|---|---|
| `kernel/`, `gateway/`, `shell/`, `mcp/`, `auth/` | **Platform** |
| `packages/**` (ui, app, contracts, module, tenancy, testing, all of them) | **Platform** |
| `modules/hub/**`, `modules/_template/**` | **Platform** |
| `scripts/**`, `tests/` (root), `.github/**`, `backup/**`, `demo/**` | **Platform** |
| `docker-compose*.yml`, `Makefile`, `.env.example`, root `pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `uv.lock`, `pnpm-lock.yaml`, `eslint.config.mjs` | **Platform** |
| `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/platform/**` | **Platform** |
| `modules/{training,vitals,macros,recipes,shopping,money,goals}/**` | **Apps-1** |
| `modules/{outings,travel,library,planner,notebook,insights,study}/**` | **Apps-2** |
| `docs/apps/<id>.md` | the owner of that module |
| `ROADMAP.md`, `TASKS.md`, `AGENTS.md`, `tests/spanish_baseline.txt` | everyone, **only the lines of your own tasks or files** |

Easy to miss:

- **A module's manifest belongs to its app owner.** Platform owns the manifest schema and its
  validator, not the manifests.
- **Dependencies belong to Platform.** Apps never add a Python or npm dependency, because that
  rewrites the root lockfiles. Ask with `needs-platform`.
- **Shared UI belongs to Platform.** A new visual piece is born in `packages/ui`. While you wait,
  build it inside the app and mark it `TODO(ui):`.
- **The long-line ignores** in the root `pyproject.toml` belong to Platform, but anyone may delete
  the line of a file they own once it no longer needs it.
- **Migrations**: each module has its own `schema/` folder and numbering. Kernel migrations are
  Platform's.

## Interfaces are frozen

Bootstrap published six interfaces with working stubs. Everyone codes against them. Platform may
change their internals, never their shape, without an issue that the app owners acknowledge.

1. **i18n.** TypeScript: `I18nProvider`, `useT()`, `createT()` from `@openarga/ui`; catalogs in
   `modules/<id>/ui/src/i18n/{en,es}.json`. Python: `arga_module.i18n.t(directory, key, locale)`
   with catalogs in `modules/<id>/src/<id>/i18n/{en,es}.json`. English is the source language;
   keys are dotted English (`week.empty`).
2. **Preferences.** `GET /api/kernel/me/preferences` returns `locale`, `timezone`, `currency`,
   `country`, `region`, `area`. TypeScript: `usePreferences()` from `@openarga/app`. Python:
   `arga_module.preferences.current()`, filled per request from the `x-arga-*` headers the gateway
   sends, falling back to the instance defaults (`OPENARGA_*` variables).
3. **AI.** Capabilities `ai.extract` and `ai.run`, models in `arga_contracts.ai`. An app names a
   role (`fast` or `smart`), never a provider or a model.
4. **Fake mode.** `CONNECTIONS_MODE=fake` makes every provider that has a double answer from
   fixtures (`hub.fake`).
5. **Demo seed.** A module joins the demo with `src/<id>/demo.py` exposing
   `async def seed(connection, persona, today)`. The cast is `demo/personas.yaml`: Alex and Sam,
   who share a space. Dates are relative to `today`, never absolute.
6. **Manifest names.** `names: {en, es}` and `summary: {en, es}` in every manifest.

## Branches, PRs and merging

- One task from `TASKS.md` per PR. Branch `p/<task>-<slug>`, `a1/<task>-<slug>` or `a2/<task>-<slug>`.
- PR title `[<task>] <conventional summary>`, e.g. `[P6] feat(hub): ai.run agent loop`.
- Rebase on `main` before opening and before merging. Rebase merge only, never squash.
- A PR merges when the full local suites are green (see Running things), with their summary
  pasted in the PR body. GitHub Actions only runs on demand (`workflow_dispatch`) until it is
  available for this repository again.
- Small PRs. Two short PRs beat one long one, because the others rebase on yours.

## ADR numbers

| Range | Who |
|---|---|
| 0001 to 0019 | Bootstrap |
| 0020 to 0039 | Platform |
| 0040 to 0059 | Apps-1 |
| 0060 to 0079 | Apps-2 |

## Language

- Everything is **English**: code, identifiers, routes, comments, strings, logs, errors, commits,
  docs, ADRs, tool descriptions and prompts.
- Spanish lives in one kind of place: the UI catalogs (`i18n/es.json`) and the `es` entries of a
  manifest's `names` and `summary`. Plus data that is Spanish by nature and is not prose: an area
  profile's search terms for a Spanish city, a Spanish bank's movement patterns.
- `tests/test_no_spanish.py` enforces it. Files that still have Spanish are listed in
  `tests/spanish_baseline.txt`; when you finish a file, remove its line. v0.1 ships with the
  baseline empty.
- Commits are conventional (`feat(outings): ...`).

## Comments

As few as possible. A comment exists only when the code cannot say it: a non-obvious *why*, a
constraint from outside, a workaround with its reason. No docstrings that restate a name, no
section banners, no history. Design rationale goes in an ADR.

## Running things

```bash
uv sync --all-packages
pnpm install
eval "$(scripts/test-databases.sh up 4 --local)"   # or without --local if Docker is there
uv run pytest -n 4
pnpm -r test && pnpm -r lint && pnpm run lint:tokens
uv run ruff check . && uv run ruff format --check .
```

Isolation tests run as the module role against a real database, never with mocks. Anything that
needs containers (the whole stack talking) waits for a machine with Docker.
