import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppNames, CLAUDE_CLIENT_ID, ConnectClaude, IconStyles, Versions } from "./Settings";
import { PlatformVersion } from "./Version";

describe("conectar Claude", () => {
  it("da lo que hay que pegar en Claude, y dice que no hace falta secreto", () => {
    const html = renderToStaticMarkup(
      <ConnectClaude origin="https://arga.example" />,
    );

    expect(html).toContain('value="https://arga.example/mcp"');
    expect(html).toContain(`value="${CLAUDE_CLIENT_ID}"`);
    expect(html).toContain("deja el secreto");
    expect(html).toContain("vacío");
  });

  it("lleva a la consola de cuenta del realm, donde se ven y se revocan los accesos", () => {
    const html = renderToStaticMarkup(
      <ConnectClaude origin="https://arga.example" />,
    );

    expect(html).toContain('href="/auth/realms/arga/account"');
  });

  it("el cliente es el del realm, y el realm lo declara público", async () => {
    const realm = await import("../../../auth/realm.json");
    const claude = realm.clients.find(
      (client: { clientId: string }) => client.clientId === CLAUDE_CLIENT_ID,
    );

    expect(claude?.publicClient).toBe(true);
  });
});

describe("versiones", () => {
  it("lista la de arga y la de cada app por separado", () => {
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

describe("la versión de arga en el escritorio", () => {
  it("se pinta discreta, con su nombre y su número", () => {
    const html = renderToStaticMarkup(<PlatformVersion version="v0.42.0" />);

    expect(html).toContain("arga");
    expect(html).toContain("v0.42.0");
    expect(html).toContain("desktop-version");
  });

  it("sin versión todavía, no deja un hueco", () => {
    expect(renderToStaticMarkup(<PlatformVersion version="" />)).toBe("");
  });
});

describe("los nombres de las apps", () => {
  const modules = [
    { id: "planner", name: "Planner", version: "1", enabled: true, api_prefix: "/api/planner", scopes: [], updated_at: "2026-09-30T00:00:00Z" },
    { id: "vitals", name: "Vitals", version: "1", enabled: true, api_prefix: "/api/vitals", scopes: [], updated_at: "2026-09-30T00:00:00Z" },
  ];

  it("con un juego elegido enseña cómo queda cada una", () => {
    const html = renderToStaticMarkup(
      <AppNames preferences={{ app_names: "greek" }} onChange={() => {}} modules={modules} />,
    );

    expect(html).toContain("Chronos · Asclepius");
    expect(html).not.toContain("<input");
  });

  it("con los tuyos, un campo por app con lo que hayas escrito", () => {
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

describe("el acabado de los iconos", () => {
  it("ofrece los tres con tus apps de muestra, y marca el elegido (ADR-0170)", () => {
    const app = (id: string) => ({ id, name: id, view: `/${id}`, updated_at: "2026-11-01T10:00:00Z" }) as never;
    const html = renderToStaticMarkup(
      <IconStyles preferences={{ icon_style: "ink" }} onChange={() => undefined} modules={[app("planner"), app("training"), app("insights")]} />,
    );

    expect(html).toContain("Color");
    expect(html).toContain("Tinta");
    expect(html).toContain("Papel");
    expect(html).toContain('src="/planner/icon-paper.svg?v=');
    expect(html).toMatch(/aria-checked="true"[^>]*>(<[^>]+>)*.*Tinta/);
  });
});

