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

Requirements: Docker, about 4 GB of RAM for the whole stack, a domain if you want to reach it from
outside your network.

The one-command setup (`docker compose up` with demo data) lands with tasks P2 and P10. Until
then, the development loop is:

```bash
uv sync --all-packages
pnpm install
eval "$(scripts/test-databases.sh up 4)"
uv run pytest -n 4
pnpm -r test
```

## Contributing

Read `AGENTS.md` first: it is the working agreement for humans and coding agents alike. Everything
in the repository is English except the Spanish UI catalogs.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
