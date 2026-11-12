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
