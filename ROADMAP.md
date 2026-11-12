# Roadmap

OpenArga is a self-hosted personal operating system: a kernel, a module contract and fifteen apps
that live on it. Every person's data is isolated by Postgres, the AI acts only through tools, and
any AI provider works.

## v0.1: first public release

Done when a stranger can clone the repository, run one command, log in and use every app, in
English or Spanish, with demo data or their own.

**In scope**

- Fifteen apps with standard names. The original Arga names stay available as a name set.
- Local login, no third-party account required. Google or any OIDC provider is optional.
- One instance config and per-person preferences: language, time zone, currency, country, region
  and home area.
- English and Spanish UI. Everything that is not UI is English.
- One AI layer for the whole system: Anthropic or any OpenAI-compatible endpoint (OpenAI, Gemini,
  Mistral, OpenRouter, Ollama, LM Studio, vLLM). Optional: without it everything works except
  automatic insights and automatic event discovery.
- Fake mode for every connection, and a demo with two synthetic people who share a space.
- Outings works for any city through an area profile. Pamplona and Munich ship as examples.
- Finance: bank by API (Enable Banking), CSV import, holdings snapshots, shared expenses.
- Docker Compose generated from the manifests; pick the apps you want.
- CI on GitHub Actions, public images, one version number for everything.
- Docs in English: install, configure, architecture, AI, build your own app.

**Out of scope for v0.1**

- Imports from third-party apps (Strong, Hevy, Goodreads) and a full data export.
- Modules installed from another repository.

## v0.2

Imports and exports, modules as installable packages, more area profiles and bank patterns from
contributors.
