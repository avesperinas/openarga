# AI

The AI does not use the app. It uses the tools.

## Tools

A tool is a function with a name, a description and parameters, declared in the manifest with its
scope. The model reads the description, decides to call it, the module runs it against Postgres
with the role its scopes grant, and returns the result. **The model never sees the schema or writes
SQL.** Read tools are broad; write tools are narrow and carry an explicit verb. There is never a
generic write tool.

## Your own client, through MCP

The MCP server at `https://<host>/mcp` aggregates the tools of every module, with OAuth 2.1 and one
scope per module and access (`training:read`, `money:write`). Any MCP client works: add it as a
custom connector in Claude, or point any other client at it. The client sees only the tools its
token's scopes allow, and every call runs as the matching Postgres role:

```
token scope → Postgres role → module schema
```

Remote clients such as claude.ai reach the server from their own infrastructure, so the endpoint
must be reachable from the internet over HTTPS.

## The platform, through the AI layer

Some features need the platform itself to call a model: reading an events page that has no feed,
or writing the weekly insights. Those calls go through one layer in the hub (ADR-0005):

- **One place to configure** the provider (Anthropic Messages, or any OpenAI-compatible endpoint:
  OpenAI, Gemini, Mistral, OpenRouter, Ollama, LM Studio, vLLM), each person's key, which model
  plays each role and the budget.
- **Apps ask for a role, never a model**: `fast` for extraction, `smart` for tasks with tools.
- **`ai.extract`**: text in, JSON validated against a schema out. No tools, no personal context.
- **`ai.run`**: a task run by an agent loop whose only outputs are OpenArga's tools, with the token
  of the app that asked (read everything, write only that app), plus `web.search` and `web.fetch`.

Without a provider, everything works except automatic insights and automatic event discovery. In
the demo and in tests, a fake provider answers.

## Configuring the AI layer

The instance sets defaults with environment variables; each person can override every one of them,
their key included, in Connections (`GET/PUT /api/hub/ai/settings`, `PUT/DELETE /api/hub/ai/key`).

| Variable | Meaning |
|---|---|
| `OPENARGA_AI_PROVIDER` | `none`, `fake`, `anthropic` or `openai`. Unset: `fake` when `CONNECTIONS_MODE=fake`, else `none`. |
| `OPENARGA_AI_BASE_URL` | Endpoint. Required for `openai` (for Ollama, `http://ollama:11434/v1`); for `anthropic`, only to go through a proxy. |
| `OPENARGA_AI_FAST_MODEL`, `OPENARGA_AI_SMART_MODEL` | The model behind each role. Anthropic defaults to `claude-haiku-5-5` and `claude-opus-5-5`; an OpenAI-compatible endpoint has no default. |
| `OPENARGA_AI_MONTHLY_TOKENS` | Tokens (input plus output) each person may spend per calendar month. Unset: no limit. |
| `OPENARGA_AI_KEY` | A shared key, used only by people who have not set their own. Not needed for Ollama. |

A person's key is stored encrypted with `HUB_CREDENTIALS_KEY` and never returned by the API.

Every call is an **attempt** in `hub.ai_attempt`: app, capability, role, provider, model, tokens,
outcome. `GET /api/hub/ai/attempts` lists a person's own with what they spent this month. When the
month's budget is spent, `ai.extract` answers `429` and the attempt is logged as `over_budget`.

`ai.extract` checks `output_schema` before calling anyone, and validates the answer against it. With
Anthropic it uses structured outputs; with an OpenAI-compatible endpoint it asks for a JSON schema
response and falls back to JSON mode where the endpoint does not support schemas.

## How `ai.run` works

`ai.run` answers at once: `queued` with a `run_id`, or `repeated` when the same app already asked
with the same `key` (a key that failed can be asked again). The hub worker then runs the task:

1. It lists OpenArga's tools as the MCP server does, with the app's scopes: every module's `read`
   and the app's own `write`. A tool that writes to another app is never offered. Calls go to each
   module with `x-arga-scopes` and the person's `x-arga-user`, so the module runs them as the
   matching Postgres role, exactly as for an MCP client.
2. With `web: true` it adds `web_fetch` and, when a search engine is configured, `web_search`.
   `web_fetch` only reaches public addresses, checks every redirect, and returns the page as text.
3. The loop stops when the model answers without calling tools, after `max_steps`, when the model
   declines, or when the month's budget runs out (`over_budget`). The attempt keeps the steps, the
   tokens and the final summary.

| Variable | Meaning |
|---|---|
| `OPENARGA_SEARXNG_URL` | A SearXNG instance with the JSON format enabled. |
| `OPENARGA_BRAVE_KEY` | A Brave Search API key, used when there is no SearXNG. |
| `AI_RUN_EVERY_SECONDS` | How often the worker looks for queued runs (default 15). |
