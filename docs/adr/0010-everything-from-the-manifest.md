# ADR-0010: Everything about an app comes from its manifest

Status: accepted

To add an app, a fork drops a folder under `modules/` and nothing else changes: the realm scopes,
the compose services, the gateway routes, the launcher entry, the icon, the names and the default
place on the dashboard are derived from `manifest.yaml`. A central list that names apps is a bug.
The kernel validates the manifest on registration; CI validates every manifest in the repository.
