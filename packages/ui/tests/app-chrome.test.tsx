import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { APP_HUES, AppBackdrop, AppHeader, backgroundOf, backgroundStyle, cameFromArga } from "../src/index";

const ORIGIN = "https://arga.example";

function storage(initial: Record<string, string> = {}) {
  const values = { ...initial };
  return {
    getItem: (key: string) => values[key] ?? null,
    setItem: (key: string, value: string) => {
      values[key] = value;
    },
  };
}

describe("volver a arga", () => {
  it("arriving from the desktop allows offering the way back", () => {
    expect(cameFromArga("recipes", `${ORIGIN}/`, ORIGIN, storage())).toBe(true);
  });

  it("and it is remembered while navigating within the app, where no referrer says it", () => {
    const remembered = storage();
    cameFromArga("recipes", `${ORIGIN}/`, ORIGIN, remembered);

    expect(cameFromArga("recipes", "", ORIGIN, remembered)).toBe(true);
  });

  it("each app remembers its own: coming to Training does not offer going back from Money", () => {
    const remembered = storage();
    cameFromArga("training", `${ORIGIN}/`, ORIGIN, remembered);

    expect(cameFromArga("money", "", ORIGIN, remembered)).toBe(false);
  });

  it("opening the installed app there is nowhere to go back to", () => {
    expect(cameFromArga("recipes", "", ORIGIN, storage())).toBe(false);
  });

  it("coming from elsewhere in the same app is not coming from arga", () => {
    expect(cameFromArga("recipes", `${ORIGIN}/recipes/receta/a1`, ORIGIN, storage())).toBe(
      false,
    );
  });

  it("nor coming from outside the hostname", () => {
    expect(cameFromArga("recipes", "https://otro.example/", ORIGIN, storage())).toBe(false);
  });

  it("without storage (private mode) it does not crash: it is simply not offered", () => {
    expect(cameFromArga("recipes", "", ORIGIN, null)).toBe(false);
  });
});

describe("an app's header", () => {
  it("carries the app's mark, the eyebrow and the title, shaped like all of them", () => {
    const html = renderToStaticMarkup(
      <AppHeader
        app={{ id: "money", name: "Money", icon: "/money/icon.svg?v=1" }}
        eyebrow="Patrimonio"
        title="Resumen"
      />,
    );

    expect(html).toContain('class="app-header"');
    expect(html).toContain('src="/money/icon.svg?v=1"');
    expect(html).toContain('<p class="app-eyebrow">Patrimonio</p>');
    expect(html).toContain('<h1 class="app-title">Resumen</h1>');
  });

  it("a screen under another carries a back with its name, which is not the exit to arga", () => {
    const html = renderToStaticMarkup(
      <AppHeader
        app={{ id: "money", name: "Money", icon: "/money/icon.svg?v=1" }}
        back={{ label: "Resumen", onClick: () => undefined }}
        title="Objetivos"
      />,
    );

    expect(html).toMatch(/<button type="button" class="app-back">.*Resumen<\/button>/);
    expect(html).not.toMatch(/class="app-back"[^>]*href/);
    expect(html).toMatch(/<a class="app-home" href="\/"/);
  });

  it("without a parent screen there is no back", () => {
    const html = renderToStaticMarkup(
      <AppHeader app={{ id: "money", name: "Money", icon: "/money/icon.svg?v=1" }} title="Resumen" />,
    );

    expect(html).not.toContain("app-back");
  });
});

describe("an app's background", () => {
  it("no photo or scrim: its colour's tint, and the app class for its styles", () => {
    const html = renderToStaticMarkup(
      <AppBackdrop app="training" className="training-desktop">
        <p>dentro</p>
      </AppBackdrop>,
    );

    expect(html).toContain('class="app-desktop training-desktop"');
    expect(html).toContain('data-background="tint"');
    expect(html).toContain("--app-background-hue:var(--hue-4)");
    expect(html).not.toContain("data-wallpaper");
    expect(html).not.toContain("wallpaper");
    expect(html).toContain("dentro");
    expect(html).not.toContain("data-kind");
  });

  it("with `colored`, the system pieces take the app's colour", () => {
    const html = renderToStaticMarkup(
      <AppBackdrop app="library" className="library-desktop" colored>
        <p>dentro</p>
      </AppBackdrop>,
    );

    expect(html).toContain('data-kind="hue-5"');
  });

  it("the choice in its Settings rules, and what no longer exists goes back to its colour", () => {
    expect(backgroundOf("training", { app_backgrounds: { training: "plain" } })).toBe("plain");
    expect(backgroundOf("training", { app_backgrounds: { training: "hue-2" } })).toBe("hue-2");
    expect(backgroundOf("training", { app_backgrounds: { training: "foto" as never } })).toBe("app");
    expect(backgroundOf("training", { app_wallpapers: { training: "duna" } })).toBe("app");
    expect(backgroundStyle("training", "plain")).toEqual({});
    expect(backgroundStyle("training", "hue-2")).toEqual({ "--app-background-hue": "var(--hue-2)" });
  });

  it("each app's colour is its manifest's", () => {
    const root = resolve(__dirname, "../../../modules");
    for (const id of readdirSync(root)) {
      const file = resolve(root, id, "manifest.yaml");
      if (id.startsWith("_") || !existsSync(file)) continue;
      const hue = /^ {2}hue: (\d+)$/m.exec(readFileSync(file, "utf8"))?.[1];
      expect([id, APP_HUES[id]]).toEqual([id, hue ? Number(hue) : undefined]);
    }
  });
});
