import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { type Notice, byDay } from "../lib/inbox";
import { InboxBody } from "./Inbox";

const notice = (id: string, sent_at: string, read = false): Notice => ({
  id,
  app: "macros",
  app_name: "Macros",
  title: `Aviso ${id}`,
  body: "Llevas 80 g de 120 g hoy.",
  href: "/macros/",
  sent_at,
  read,
});

const NOW = new Date(2026, 9, 29, 12, 0);
const at = (day: number, hour: number) => new Date(2026, 9, day, hour, 0).toISOString();

const body = (loaded: Parameters<typeof InboxBody>[0]["loaded"], online = true) =>
  renderToStaticMarkup(
    <InboxBody
      loaded={loaded}
      online={online}
      name={(one) => one.app_name}
      onRetry={() => undefined}
      onOpen={() => undefined}
      onSettings={() => undefined}
    />,
  );

describe("la bandeja de avisos", () => {
  it("por día, del más nuevo al más viejo: Hoy, Ayer y la fecha", () => {
    const days = byDay([notice("a", at(27, 9)), notice("b", at(29, 8)), notice("c", at(28, 20)), notice("d", at(29, 10))], NOW);

    expect(days.map((day) => [day.label, day.notices.map((n) => n.id)])).toEqual([
      ["Hoy", ["d", "b"]],
      ["Ayer", ["c"]],
      ["Martes, 27 de octubre", ["a"]],
    ]);
  });

  it("cada aviso lleva a su app y dice si aún no se ha abierto, sin contador", () => {
    const html = body({ state: "ready", notices: [notice("a", at(29, 8)), notice("b", at(29, 9), true)] });

    expect(html).toContain('href="/macros/"');
    expect(html.match(/data-unread/g)).toHaveLength(1);
    expect(html).toContain("(sin abrir)");
    expect(html).toContain("Llevas 80 g de 120 g hoy.");
  });

  it("cargando, un esqueleto; con error, Reintentar; sin red, lo dice", () => {
    expect(body({ state: "loading" })).toContain('aria-busy="true"');
    expect(body({ state: "error" })).toContain("Reintentar");
    expect(body({ state: "error" }, false)).toContain("Sin conexión");
  });

  it("vacía, dice qué es y lleva a elegir los avisos", () => {
    const html = body({ state: "ready", notices: [] });

    expect(html).toContain("Ningún aviso en 30 días");
    expect(html).toContain("Elegir qué avisos llegan");
  });
});
