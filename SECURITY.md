# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through GitHub: the repository's
**Security** tab, **Report a vulnerability**. Say what is affected, how to reproduce it and what an
attacker gains. You will get an answer within a week, and a fix or a plan before anything is made
public. Credit goes to you in the advisory unless you prefer otherwise.

## Supported versions

OpenArga is in its v0.x series: only the latest release and `main` receive security fixes.

## The model it defends

- **Isolation by Postgres.** Each module connects with its own role, which has grants only on its
  own schema. Every row that belongs to a person is filtered by forced row-level security, so a
  query cannot see another person's rows even if the code asks for them.
- **One identity chain.** People sign in once through Keycloak behind the gateway. Services never
  receive passwords or tokens, only the identity, scopes and spaces the gateway injects; headers a
  client sends with those names are dropped.
- **Permission = OAuth scope = Postgres role.** A tool, an API call or an MCP call with a read
  scope runs as the module's read role, so it cannot write.
- **The AI acts only through tools.** Models never see a schema or write SQL. In demo mode the MCP
  server is read-only.
- **Secrets stay out of the repository.** They live in `.env`; provider credentials are encrypted
  per person in the Connections app.
- **No personal data in the repository.** Seeds, fixtures and tests are synthetic.

What is outside: the host you run it on, its TLS termination, your backups and who you give an
account to.
