# ADR-0003: An event log, an entity registry, and a hub for outside data

Status: accepted

There is no universal schema. The kernel keeps an append-only event log (`kernel.events`), with an
idempotency key per event, and a registry of entities with identity and aliases
(`kernel.entities`, `kernel.entity_aliases`): "SUPERMARKET 4412 MADRID" and "Supermarket" are the
same merchant.

Everything that comes from outside (banks, health platforms, calendars, weather, books, food,
places, agendas) is brought by one module, the **hub** (Connections). A provider is a file in the
hub; a new account is a plug, not code. What it brings is published under its category with a
written contract (`arga_contracts.sources`), and each app declares in `inlets` which contracts it
accepts. The hub's own schema stores how each source is reached and how each attempt went, never
the data itself.

Apps ask the hub for one-off lookups (search a book, geocode a place, get a forecast) through
capabilities declared in `uses`, routed by the kernel.
