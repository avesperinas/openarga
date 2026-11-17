import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppBackdrop, AppSettings, ARGA_SETTINGS, SETTINGS_TAB } from "../src/index";

const APP = { id: "training", name: "Training", icon: "/training/icon.svg?v=1" };

describe("los ajustes de una app", () => {
  it("son la última pestaña, con el mismo nombre y el mismo icono en todas", () => {
    expect(SETTINGS_TAB).toMatchObject({ id: "settings", label: "Settings", icon: "settings" });
  });

  it("llevan lo de la app arriba y debajo, en el mismo orden, el fondo y la versión", () => {
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

  it("el fondo se elige solo si hay fondo de app que elegir", () => {
    const html = renderToStaticMarkup(<AppSettings app={APP} />);
    expect(html).not.toContain("Fondo de Training");
    expect(html).toContain("About");
  });

  it("los de arga se abren desde su escritorio", () => {
    expect(ARGA_SETTINGS).toBe("/#settings");
  });
});
