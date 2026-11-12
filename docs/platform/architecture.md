# Architecture

## Layers

1. **Connections hub** (`modules/hub`). Everything that comes from outside: one provider file per
   source, its schedule and retries, credentials encrypted per person. It publishes what it brings
   to the kernel's event log under a category (`finance.movement`, `health.sleep`), with a written
   contract, and answers one-off lookups (search a book, geocode a place) as capabilities.
2. **Canonical data.** One Postgres. `kernel.*` holds the event log, the entity registry, the
   module registry, people and spaces. Each module has its own schema, role and read role.
3. **Services.** Kernel, gateway, MCP server and one service per module, each in its own container.
4. **Shell and apps.** A Next.js PWA with the dashboard and launcher, and one React + Vite app per
   module, all drawn with `packages/ui`.

## The canonical model

There is no universal schema. An append-only event log plus a registry of entities with identity:

- `kernel.events`: everything that happened, when it happened and when we learned it, with the
  module and source that published it, its type, its payload and a unique idempotency key.
- `kernel.entities` and `kernel.entity_aliases`: things with identity (an account, a merchant, an
  exercise, a food) and the many ways sources write them. Resolution is automatic, keeps its trail,
  and can be undone.
- `kernel.modules`: registered modules and their validated manifests.

## Flow

```
provider → hub → POST /events (idempotency key) → kernel.events
                                                     │
                                         each app reads its view <id>.events
                                                     │
app ← derives its own tables ← API ← widget, app screen, MCP tool
```

What a person types in an app is written by the app to its own schema (the source of truth), queued
in `<id>_outbox` in the same transaction, and published to the log by the module's publisher.

## Isolation

- A module connects as `svc_<id>`, member of `mod_<id>` only. Read tools and widgets run as
  `mod_<id>_read`.
- Module to module calls are forbidden. Sharing happens by contract (`publishes`, `receives`,
  `provides`, `uses`) through the kernel, which checks the manifest.
- The gateway logs people in once and injects identity, scopes, spaces and preferences into every
  service as headers. Modules never implement login.
- Every person-owned row is filtered by forced row-level security from `arga.user_id`
  (ADR-0004).

## Why not a database per service

The value of the system is in crossing domains. With a database per service a join becomes a
pipeline between APIs. See ADR-0002.
