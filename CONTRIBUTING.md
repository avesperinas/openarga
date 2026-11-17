# Contributing

Thank you for helping. OpenArga is built by people and coding agents under the same rules; read
`AGENTS.md` for the whole agreement and `docs/adr/0001-principles.md` for the principles behind it.

## Set up

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm (`corepack enable`)
and Postgres 16, either through Docker or installed locally.

```bash
uv sync --all-packages
pnpm install
eval "$(scripts/test-databases.sh up 4)"          # Docker; add --local to use a local Postgres
```

## Before you open a pull request

Every suite must be green on your branch, rebased on `main`:

```bash
uv run pytest -n 4
uv run ruff check . && uv run ruff format --check .
pnpm -r --no-bail test
pnpm -r --no-bail lint
pnpm run lint:tokens
```

Paste their summary in the pull request. Isolation tests run as the module role against a real
Postgres, never with mocks.

## The rules a change follows

- **Modules never call each other**; they ask the kernel, which checks the manifest.
- **One Postgres schema and one role per module**, and every table declares its class and has
  row-level security.
- **Every migration is backward compatible**: the previous version must boot on the new schema.
- **No colours, spacing, radii or fonts outside `packages/ui` tokens** (`pnpm run lint:tokens`).
- **The AI acts only through tools**, each with its scope.
- **Zero personal data**: seeds, fixtures and tests are synthetic.
- **English everywhere** (code, comments, commits, docs). Spanish lives only in the UI catalogs
  (`i18n/es.json`) and the `es` names in manifests; `tests/test_no_spanish.py` checks it.
- **Few comments**: only the *why* the code cannot say. Design decisions go in an ADR.

## Pull requests

- One task per pull request, small. Title `[<task>] <conventional summary>`, for example
  `[P6] feat(hub): ai.run agent loop`. Commits are conventional (`feat(outings): ...`).
- Rebase on `main` before opening and before merging. Pull requests merge by rebase, never squash.
- A new app starts with `scripts/new-module.sh <id> <Name>`; see `docs/platform/module-contract.md`.
- New dependencies, shared UI pieces and the manifest schema belong to the platform: open an issue
  if you need one.

## Reporting bugs and ideas

Open a GitHub issue with what you did, what you expected and what happened. For anything that
could be a vulnerability, follow `SECURITY.md` instead.
