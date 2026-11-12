# ADR-0006: Every migration is backward compatible, and the old code must boot

Status: accepted

A rollback returns the code, not the schema, and the new version may have been writing for a while
before it happens. So the previous release must **boot** against the new schema, not only answer its
endpoints: the container migrates before serving, and a `migrate` that does not tolerate a database
ahead of it dies before reaching them.

Rename or drop a column in three releases: add and write both; stop reading the old one; drop it.
The verification of any schema change is booting the previous image against the new schema.

The open edition starts with one baseline migration per module. From there, every change follows
this rule.
