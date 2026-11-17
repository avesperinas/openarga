import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppBackdrop, AppSettings, ARGA_SETTINGS, SETTINGS_TAB } from "../src/index";

const APP = { id: "training", name: "Training", icon: "/training/icon.svg?v=1" };

describe("an app's settings", () => {
  it("they are the last tab, with the same name and icon in all", () => {
    expect(SETTINGS_TAB).toMatchObject({ id: "settings", label: "Settings", icon: "settings" });
  });

  it("carry the app's own above and below, in the same order, the background and the version", () => {
    const html = renderToStaticMarkup(
      <AppBackdrop app="training">
        <AppSettings app={APP}>
          <p>Weekly goal</p>
        </AppSettings>
      </AppBackdrop>,
    );

    expect(html).toContain('<h1 class="app-title">Settings</h1>');
    const own = html.indexOf("Weekly goal");
    const wallpaper = html.indexOf("Training background");
    const about = html.indexOf("About");
    expect(own).toBeGreaterThan(0);
    expect(wallpaper).toBeGreaterThan(own);
    expect(about).toBeGreaterThan(wallpaper);
    expect(html).toMatch(/aria-pressed="true"[^>]*>.*Its colour/);
    expect(html).toContain("OpenArga settings");
  });

  it("the background is chosen only if there is an app background to choose", () => {
    const html = renderToStaticMarkup(<AppSettings app={APP} />);
    expect(html).not.toContain("Fondo de Training");
    expect(html).toContain("About");
  });

  it("arga's open from its desktop", () => {
    expect(ARGA_SETTINGS).toBe("/#settings");
  });
});
