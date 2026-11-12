# ADR-0001: The principles

Status: accepted

These twelve rules are why the project exists. Changing one needs a new ADR.

1. **The kernel rules.** Modules never call each other. If one app needs data from another, it asks
   the kernel and the kernel checks the manifest.
2. **What comes from outside enters through the hub.** Connections write only to `kernel.events`
   and `kernel.entities`, never to a module's tables; modules derive their own tables from the event
   log. The single exception is what a person types into an app: the app writes it to its own
   schema, which is the source of truth, and publishes it to the log for the rest of the system.
   Outside data is named by its category (`finance.balance`), has a written contract validated on
   publish, and each app accepts it through an **inlet** without naming the provider.
3. **One Postgres schema and one role per module.** Isolation comes from the database, not from the
   process. No module has a grant on another module's schema.
4. **Every module honours the full contract**: manifest, schema, API, tools, UI. No special modules.
5. **No module defines colours, spacing, radii or fonts.** It consumes the tokens of `packages/ui`.
   CI checks it.
6. **Tools are the only surface through which the AI acts on your behalf.** The model never sees the
   raw schema or writes SQL. Read tools are broad; write tools are narrow and carry an explicit
   verb. Apart from that, the platform may call a model as an internal component, always through the
   AI layer, with narrow input, narrow output, no access to the schema and no more context than the
   call carries.
7. **Permission = OAuth scope = Postgres role.** The same authorisation chain for the UI, the API and
   the AI.
8. **Nothing ships without green CI.** Images are built and published by CI from `main`; nobody
   deploys by hand.
9. **Every change delivers a vertical increment**: something visible in the UI, in a tool or in an
   endpoint. No PRs that only add layers.
10. **Zero personal data in the repository.** Seeds and tests are synthetic. A real email address is
    personal data even as the subject of a test. A real value that is truly needed is configuration
    and goes in a secret.
11. **Every migration is backward compatible.** The previous code must be able to **boot** and serve
    against the new schema. Add, write to both, stop reading the old, and only in a later release
    remove it. A rollback returns the code, not the schema.
12. **No query sees another person's rows, and Postgres guarantees it, not the code.** Every table
    declares in its comment whether it belongs to a person (`arga:person`), a catalogue
    (`arga:catalog`), a shared space (`arga:shared`) or the system (`arga:system`); the first three
    carry `user_id` and forced RLS, shared ones also `space_id`. Each transaction sets the person in
    the `arga.user_id` setting and their spaces in `arga.space_ids`. A hand-written
    `where user_id = ...` is not isolation.
