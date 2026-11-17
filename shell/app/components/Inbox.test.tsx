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
  body: "You have 80 g of 120 g today.",
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

describe("the notification inbox", () => {
  it("by day, newest first: Today, Yesterday and the date", () => {
    const days = byDay([notice("a", at(27, 9)), notice("b", at(29, 8)), notice("c", at(28, 20)), notice("d", at(29, 10))], NOW);

    expect(days.map((day) => [day.label, day.notices.map((n) => n.id)])).toEqual([
      ["Today", ["d", "b"]],
      ["Yesterday", ["c"]],
      ["Tuesday 27 October", ["a"]],
    ]);
  });

  it("each notification links to its app and says if it is still unread, with no counter", () => {
    const html = body({ state: "ready", notices: [notice("a", at(29, 8)), notice("b", at(29, 9), true)] });

    expect(html).toContain('href="/macros/"');
    expect(html.match(/data-unread/g)).toHaveLength(1);
    expect(html).toContain("(unread)");
    expect(html).toContain("You have 80 g of 120 g today.");
  });

  it("loading, a skeleton; on error, Try again; offline, it says so", () => {
    expect(body({ state: "loading" })).toContain('aria-busy="true"');
    expect(body({ state: "error" })).toContain("Try again");
    expect(body({ state: "error" }, false)).toContain("without a connection");
  });

  it("empty, it says what it is and leads to choosing notifications", () => {
    const html = body({ state: "ready", notices: [] });

    expect(html).toContain("No notifications in 30 days");
    expect(html).toContain("Choose which notifications arrive");
  });
});
