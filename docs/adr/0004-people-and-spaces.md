# ADR-0004: Every row belongs to someone, and spaces are shared

Status: accepted

Several people use the same instance, each isolated from the others. Every table declares its class
in its comment. Rows of a person carry `user_id` with a default taken from the transaction setting
`arga.user_id`, so code never fills it. Forced row-level security filters every query.

A **space** is a group of people (a household, a couple, a trip) that share rows. Shared tables
(`arga:shared`) carry `space_id`; a row with a space is visible to and editable by its members,
whose spaces travel in `arga.space_ids`. Creating, inviting and joining spaces belong to the kernel.

`kernel/tests/test_table_classes.py` fails on a table without a class, and
`test_tenant_isolation.py` proves the isolation as the unprivileged roles, because the superuser
used by tests skips RLS.
