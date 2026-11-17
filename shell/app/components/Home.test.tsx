import { Writable } from "node:stream";

import * as React from "react";
import { renderToPipeableStream, renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { DesktopLayout } from "../lib/kernel";
import type { Contributor } from "../lib/panels";
import { Dashboard } from "./Dashboard";
import { Ask, HomeProvider, PanelPage } from "./Home";
import { HomePanelsSettings } from "./Settings";

const money: Contributor = {
  source: "money",
  name: "Money",
  panel: {
    area: "money",
    headlines: [{ text: "You reach the end of the month with 420 € to spare", emphasis: "420 €", tone: "positive", status: "+420 €" }],
    tabs: [
      { id: "resumen", label: "Resumen", blocks: [{ type: "figure", label: "Patrimonio", value: "48.200 €" }] },
      { id: "spending", label: "Spending", blocks: [{ type: "figure", label: "This month", value: "1.240 €" }] },
    ],
  },
};

const layout: DesktopLayout = { updated_at: null, default: true, placements: {}, pages: [{ id: "una", items: [] }] };

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

describe("panels as pages", () => {
  it("a panel is one more widget: it shares a page with the others and names its tab", async () => {
    let arrive!: (found: Contributor[]) => void;
    const pending = new Promise<Contributor[]>((resolve) => (arrive = resolve));
    const mixed: DesktopLayout = {
      ...layout,
      pages: [
        {
          id: "money",
          items: [
            { instance_id: "p", source: "panel", widget: "money", size: "4x6" },
            { instance_id: "t", source: "panel", widget: "money.tab", size: "2x2", option: "money.spending" },
          ],
        },
        { id: "other", items: [] },
      ],
    };
    const { first, all } = await stream(
      <HomeProvider>
        <Dashboard desks={{ mobile: mixed, desktop: mixed }} device="mobile" catalogue={[]} panels={{ money: pending }} />
      </HomeProvider>,
      () => arrive([money]),
    );
    const tabs = [...first.matchAll(/class="page-tab"[^>]*>(?:<span[^>]*>.*?<\/span>)?([^<]+)<\/button>/g)].map((match) => match[1]);
    expect(tabs).toEqual(["Money", "Widgets"]);
    expect(first).toContain('aria-busy="true"');
    expect(first).not.toContain("420 €");
    expect(all).toContain("You reach the end of the month with");
    expect(all).toContain("1.240 €");
    expect((all.match(/data-single=""/g) ?? []).length).toBe(1);
  });

  it("on the phone, one tab at a time; on the computer, all at once in columns", async () => {
    const ready = Promise.resolve([money]);
    const mobile = await stream(<PanelPage area="money" initial={ready} board={false} />, () => {});
    const desktop = await stream(<PanelPage area="money" initial={ready} board />, () => {});
    expect(mobile.all).toContain('role="tablist"');
    expect(mobile.all).toContain("48.200 €");
    expect(mobile.all).not.toContain("1.240 €");
    expect(desktop.all).toContain("area-panel-board");
    expect(desktop.all).toContain("48.200 €");
    expect(desktop.all).toContain("1.240 €");
  });

  it("while editing, each panel page moves and is removed", () => {
    const html = renderToStaticMarkup(<PanelPage area="health" board={false} editing first />);
    expect(html).toContain("Remove the Health panel");
    expect(html).toMatch(/disabled=""[^>]*aria-label="Move Health to the left"/);
  });

  it("the question shows at the top without requesting anything on open", () => {
    const html = renderToStaticMarkup(
      <HomeProvider>
        <Ask />
      </HomeProvider>,
    );
    expect(html).toContain('aria-label="Ask your apps"');
  });
});

describe("home settings", () => {
  it("the seven areas in the saved order; without a choice, only the starting ones on", () => {
    const chosen = renderToStaticMarkup(
      <HomePanelsSettings
        preferences={{ theme: "system", wallpaper: "", glass_opacity: 1, home_panels: { order: ["money"], hidden: ["mind"] } }}
        onChange={() => {}}
      />,
    );
    expect(chosen.indexOf("Money")).toBeLessThan(chosen.indexOf("Day"));
    expect((chosen.match(/role="switch"/g) ?? []).length).toBe(7);
    expect((chosen.match(/aria-checked="true"/g) ?? []).length).toBe(6);

    const fresh = renderToStaticMarkup(<HomePanelsSettings preferences={{ theme: "system", wallpaper: "", glass_opacity: 1 }} onChange={() => {}} />);
    expect((fresh.match(/aria-checked="true"/g) ?? []).length).toBe(3);
  });
});
