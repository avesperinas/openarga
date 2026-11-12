# ADR-0005: One AI layer, any provider

Status: accepted

## Context

The original system drove a Claude subscription from the server. That ties every installation to one
vendor and to terms that do not allow it in a product.

## Decision

Two ways for AI to touch your data, and only two:

1. **Your own client, through MCP.** Any MCP client (Claude, ChatGPT, a local agent) reads and acts
   through the tools, with the scopes you granted. The server pays no model.
2. **The platform, through the AI layer** in the hub. One place configures the provider (Anthropic
   Messages or any OpenAI-compatible endpoint, Ollama included), the key of each person, which model
   plays each role and the budget. Apps ask for a role, never a model:
   - `ai.extract`: text in, JSON validated against a schema out. No tools, no personal context.
   - `ai.run`: a task executed by an agent loop whose only outputs are OpenArga's MCP tools, with the
     token of the app that asked (read everything, write only that app), plus `web.search` and
     `web.fetch`.

Without a provider everything works except automatic insights and automatic event discovery.
