# Module contract

Every module has the same shape. `scripts/new-module.sh <id> <Name>` produces it from
`modules/_template`, which is the living reference of this document.

```
modules/<id>/
  manifest.yaml     identity, permissions, inlets, tools, widgets, names
  schema/           its migrations, every table prefixed <id>_; the first is 0001_init.sql
  src/<id>/         the service: main.py on the service kit, its domain, tools.py, widgets.py
  tools/glossary.md the terms of the domain, given to the model with the tools
  ui/               its app, if it has one (React + Vite on @openarga/app)
  tests/            with the shared fixtures and contract tests (arga_testing)
  Dockerfile
```

## manifest.yaml

```yaml
id: vitals
name: Health
names: {en: Health, es: Salud}
summary: {en: "Steps, sleep, heart, weight and lab results.", es: "..."}
version: 0.1.0

database:
  schema: vitals
  role: mod_vitals
  reads: []

inlets:
  - id: steps
    title: Steps
    contracts: [health.steps]

uses: [places.search]
publishes:
  - type: vitals.weight
    contract: body_weight

api:
  prefix: /api/vitals

tools:
  - name: get_weight
    scope: vitals:read
    description: >
      Weight over a date range. Use it when the question is about how weight is changing.
  - name: log_weight
    scope: vitals:write
    description: Records one manual weight measurement.

ui:
  view: /vitals
  family: health
  widgets:
    - id: weight
      title: Weight
      kind: kpi
      sizes: ["2x1", "2x2"]
      endpoint: /api/vitals/widgets/weight
      refresh: 300
      link: /vitals
```

## Rules

- **Every table says whose it is** with `comment on table ... is 'arga:person'` (or `arga:catalog`,
  `arga:shared`, `arga:system`). Person tables carry
  `user_id uuid default nullif(current_setting('arga.user_id', true), '')::uuid`; code never fills
  it. Shared tables also carry `space_id`. A kernel test fails on a table that forgets.
- **What comes from outside arrives through an inlet.** An inlet lists the source contracts it
  accepts; any provider that produces one reaches the app without touching it. The app never names
  a provider (a hub test checks it).
- **Sharing between apps is by contract**: `publishes` (own event types that fulfil a contract),
  `receives` (contracts it reads), `provides` (services it answers when another app asks through the
  kernel) and `uses` (capabilities it asks for).
- **Every published event declares its identity** in its idempotency key: the id of the row that
  tells it, never a hash of variable content.
- **Tools declare their scope**, `<id>:read` or `<id>:write`, the same string as the OAuth scope and
  the Postgres role. A write that arrives with the read role is refused by Postgres, and the module
  turns `permission denied` into 403.
- **Tool descriptions explain concepts, not fields.** "Weekly volume is measured in effective sets
  per muscle group" is worth more than documenting the table.
- **Widgets answer the same envelope**: `state` (`ready`, `empty`, `error`, `disconnected`),
  `updated_at`, an optional quantified `uncertainty`, and a `body` whose shape is fixed by the
  widget's `kind`. The system draws it, not the module.
- **Everything an app deletes goes through `ConfirmDelete`** from `packages/ui`, which says what is
  deleted and asks for a button that says exactly that.
- **Credentials of outside sources live in the hub**, encrypted. A table with `ciphertext bytea` is
  sealed: only the module's write role touches it, and no endpoint returns the value.

## Registration

A module registers itself when it boots, from its own image: `python -m arga_module` sends its
manifest to the kernel, which validates it, provisions the schema and roles, applies the pending
SQL as the module's role and forces RLS. Unknown keys are rejected: a misspelt key is a permission
you thought you declared. CI runs the same validation over every manifest in the repository.

## The service kit

`arga_module.service.Service` mounts what every module serves the same way: health probes,
`/version`, widgets on the read role, tools on the role their scopes grant, domain errors mapped to
404 and 409, per-request preferences, and the built app. `arga_module.publisher.Publisher` empties
the outbox inside the API process as soon as something is queued. `arga_testing` gives the shared
fixtures and the contract tests every module passes.

## Taking part in the demo

A module joins the demo with `src/<id>/demo.py`:

```python
async def seed(connection, persona, today) -> None: ...
```

It writes synthetic data for one person of `demo/personas.yaml`, with dates relative to `today`,
and must be idempotent.
