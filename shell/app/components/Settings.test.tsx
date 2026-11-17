import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppNames, CLAUDE_CLIENT_ID, ConnectClaude, IconStyles, Versions } from "./Settings";
import { PlatformVersion } from "./Version";

describe("conectar Claude", () => {
  it("gives what to paste into Claude, and says no secret is needed", () => {
    const html = renderToStaticMarkup(
      <ConnectClaude origin="https://arga.example" />,
    );

    expect(html).toContain('value="https://arga.example/mcp"');
    expect(html).toContain(`value="${CLAUDE_CLIENT_ID}"`);
    expect(html).toContain("leave the secret");
    expect(html).toContain("empty");
  });

  it("links to the realm's account console, where access is seen and revoked", () => {
    const html = renderToStaticMarkup(
      <ConnectClaude origin="https://arga.example" />,
    );

    expect(html).toContain('href="/auth/realms/arga/account"');
  });

  it("the client is the realm's, and the realm declares it public", async () => {
    const realm = await import("../../../auth/realm.json");
    const claude = realm.clients.find(
      (client: { clientId: string }) => client.clientId === CLAUDE_CLIENT_ID,
    );

    expect(claude?.publicClient).toBe(true);
  });
});

describe("versiones", () => {
  it("lists arga's and each app's separately", () => {
    const html = renderToStaticMarkup(
      <Versions
        platform="v0.42.0"
        modules={[
          { id: "training", version: "v1.2.0" },
          { id: "library", version: "v0.4.0" },
        ] as never}
      />,
    );

    expect(html).toContain("v0.42.0");
    expect(html).toContain("training");
    expect(html).toContain("v1.2.0");
    expect(html).toContain("library");
    expect(html).toContain("v0.4.0");
  });
});

describe("arga's version on the desktop", () => {
  it("renders discreetly, with its name and number", () => {
    const html = renderToStaticMarkup(<PlatformVersion version="v0.42.0" />);

    expect(html).toContain("arga");
    expect(html).toContain("v0.42.0");
    expect(html).toContain("desktop-version");
  });

  it("with no version yet, it leaves no gap", () => {
    expect(renderToStaticMarkup(<PlatformVersion version="" />)).toBe("");
  });
});

describe("app names", () => {
  const modules = [
    { id: "planner", name: "Planner", version: "1", enabled: true, api_prefix: "/api/planner", scopes: [], updated_at: "2026-09-30T00:00:00Z" },
    { id: "vitals", name: "Vitals", version: "1", enabled: true, api_prefix: "/api/vitals", scopes: [], updated_at: "2026-09-30T00:00:00Z" },
  ];

  it("with a set chosen it shows how each one looks", () => {
    const html = renderToStaticMarkup(
      <AppNames preferences={{ app_names: "greek" }} onChange={() => {}} modules={modules} />,
    );

    expect(html).toContain("Chronos · Asclepius");
    expect(html).not.toContain("<input");
  });

  it("with your own, one field per app with what you wrote", () => {
    const html = renderToStaticMarkup(
      <AppNames
        preferences={{ app_names: "custom", custom_app_names: { planner: "Agenda" } }}
        onChange={() => {}}
        modules={modules}
      />,
    );

    expect(html).toContain('value="Agenda"');
    expect(html).toContain('placeholder="Vitals"');
  });
});

describe("icon finish", () => {
  it("offers the three with your sample apps, and marks the chosen one (ADR-0170)", () => {
    const app = (id: string) => ({ id, name: id, view: `/${id}`, updated_at: "2026-11-01T10:00:00Z" }) as never;
    const html = renderToStaticMarkup(
      <IconStyles preferences={{ icon_style: "ink" }} onChange={() => undefined} modules={[app("planner"), app("training"), app("insights")]} />,
    );

    expect(html).toContain("Colour");
    expect(html).toContain("Ink");
    expect(html).toContain("Paper");
    expect(html).toContain('src="/planner/icon-paper.svg?v=');
    expect(html).toMatch(/aria-checked="true"[^>]*>(<[^>]+>)*.*Ink/);
  });
});

