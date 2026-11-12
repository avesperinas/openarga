# ADR-0008: One version for everything, CI on GitHub Actions

Status: accepted

The original system released each app on its own train and published from a self-hosted shipper.
For people who install OpenArga that is noise. One version number covers every image; a tag on
`main` builds and publishes them all. CI runs on GitHub Actions: Python tests against real Postgres,
TypeScript tests and lint, token lint, manifest validation, the language guard and a secret scan.
