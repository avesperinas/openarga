import { Writable } from "node:stream";

import * as React from "react";
import { renderToPipeableStream, renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CatalogueEntry, DesktopLayout, Envelope } from "../lib/kernel";
import { Dashboard } from "./Dashboard";

const NEXT: CatalogueEntry = {
  source: "training",
  id: "next",
  title: "Next session",
  hue: 1,
  kind: "kpi",
  shape: "number",
  sizes: ["2x2", "4x2"],
  endpoint: "/api/training/widgets/next",
  refresh: 300,
  link: "/training/siguiente",
};

const layout: DesktopLayout = {
  updated_at: "2026-09-18T10:00:00Z",
  default: false,
  placements: {},
  pages: [
    {
      id: "pantalla",
      items: [{ instance_id: "one", source: "training", widget: "next", size: "2x2" }],
    },
  ],
};

const envelope: Envelope = {
  state: "ready",
  updated_at: "2026-09-18T10:00:00Z",
  body: { value: "Pull", icon: "pull" },
};

const render = (entry: CatalogueEntry) =>
  renderToStaticMarkup(
    <Dashboard
      desks={{ mobile: layout, desktop: layout }}
      device="mobile"
      catalogue={[entry]}
      data={{ "training/next": envelope }}
    />,
  );

describe("the card that opens its app", () => {
  it("carries the link in the server HTML, not in a click handler", () => {
    const html = render(NEXT);

    expect(html).toContain('href="/training/siguiente"');
    expect(html).toContain('class="grid-open"');
  });

  it("says where it leads, because the link itself is empty", () => {
    expect(render(NEXT)).toContain('aria-label="Open Next session"');
  });

  it("a widget that leads nowhere renders no link", () => {
    expect(render({ ...NEXT, link: null })).not.toContain("grid-open");
  });
});

describe("one desktop for the phone and another for the computer", () => {
  const LAST: CatalogueEntry = { ...NEXT, id: "last", title: "Last session", link: null };
  const phone: DesktopLayout = {
    ...layout,
    pages: [{ id: "m", items: [{ instance_id: "m1", source: "training", widget: "next", size: "2x2" }] }],
  };
  const computer: DesktopLayout = {
    ...layout,
    pages: [{ id: "d", items: [{ instance_id: "d1", source: "training", widget: "last", size: "2x2" }] }],
  };
  const on = (device: "mobile" | "desktop") =>
    renderToStaticMarkup(
      <Dashboard
        desks={{ mobile: phone, desktop: computer }}
        device={device}
        catalogue={[NEXT, LAST]}
        data={{ "training/next": envelope, "training/last": envelope }}
      />,
    );

  it("the server renders the one of the device it guesses, and only that one", () => {
    expect(on("mobile")).toContain('data-instance="m1"');
    expect(on("mobile")).not.toContain('data-instance="d1"');
    expect(on("desktop")).toContain('data-instance="d1"');
    expect(on("desktop")).not.toContain('data-instance="m1"');
  });
});

describe("within a device, each width with its place", () => {
  const dos: DesktopLayout = {
    ...layout,
    pages: [
      {
        id: "pantalla",
        items: [
          { instance_id: "a", source: "training", widget: "next", size: "4x2" },
          { instance_id: "b", source: "training", widget: "next", size: "4x2" },
        ],
      },
    ],
    placements: { desktop: { pantalla: { b: [8, 0] } } },
  };

  it("each card leaves the server with its place in the three formats", () => {
    const html = renderToStaticMarkup(
      <Dashboard
        desks={{ mobile: dos, desktop: dos }}
        device="desktop"
        catalogue={[NEXT]}
        data={{ "training/next": envelope }}
      />,
    );

    expect(html).toContain("--xm:1;--ym:3");
    expect(html).toContain("--xt:5;--yt:1");
    expect(html).toContain("--xd:9;--yd:1");
  });
});

describe("the home page waits for no widget (T-V06)", () => {
  const stream = (element: React.ReactElement, arrive: () => void) =>
    new Promise<{ first: string; all: string }>((resolve, reject) => {
      let html = "";
      let first = "";
      const sink = new Writable({
        write(chunk, _encoding, done) {
          html += chunk.toString();
          done();
        },
        final(done) {
          resolve({ first, all: html });
          done();
        },
      });
      const { pipe } = renderToPipeableStream(element, {
        onShellReady() {
          pipe(sink);
          setTimeout(() => {
            first = html;
            arrive();
          }, 20);
        },
        onShellError: reject,
        onError: reject,
      });
    });

  it("sends the page with the card as a skeleton and completes it when its envelope arrives", async () => {
    let arrive!: (envelope: Envelope) => void;
    const slow = new Promise<Envelope | null>((resolve) => (arrive = resolve));

    const { first, all } = await stream(
      <Dashboard
        desks={{ mobile: layout, desktop: layout }}
        device="mobile"
        catalogue={[NEXT]}
        pending={{ "training/next": slow }}
      />,
      () => arrive(envelope),
    );

    expect(first).toContain('href="/training/siguiente"');
    expect(first).toContain('data-state="loading"');
    expect(first).not.toContain("Pull");
    expect(all).toContain("Pull");
  });
});
