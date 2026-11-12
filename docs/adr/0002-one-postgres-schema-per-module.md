# ADR-0002: One Postgres, one schema and one role per module

Status: accepted

## Context

The value of a personal system is in crossing domains: what you spend eating out against your weight
against how often you train. With a database per service that stops being a join and becomes a
pipeline between APIs.

## Decision

One Postgres cluster. The kernel owns `kernel.*`. Each module owns one schema with the same name as
its id, one role `mod_<id>` that can write it and one role `mod_<id>_read` that can only read it.
Every table carries the `<id>_` prefix. A service connects as `svc_<id>`, a member of `mod_<id>` only.

Crossing domains happens through the event log and the kernel, never through grants on another
schema.

## Consequences

Isolation tests run as the module role against a real database. A permission granted by mistake is
only visible when you run as the role that has it.
