import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppBackdrop, AppSettings, ARGA_SETTINGS, SETTINGS_TAB } from "../src/index";

const APP = { id: "training", name: "Training", icon: "/training/icon.svg?v=1" };

describe("los ajustes de una app", () => {
  it("son la última pestaña, con el mismo nombre y el mismo icono en todas", () => {
    expect(SETTINGS_TAB).toEqual({ id: "settings", label: "Ajustes", icon: "settings" });
  });

  it("llevan lo de la app arriba y debajo, en el mismo orden, el fondo y la versión", () => {
    const html = renderToStaticMarkup(
      <AppBackdrop app="training">
        <AppSettings app={APP}>
          <p>Objetivo semanal</p>
        </AppSettings>
      </AppBackdrop>,
    );

    expect(html).toContain('<h1 class="app-title">Ajustes</h1>');
    const own = html.indexOf("Objetivo semanal");
    const wallpaper = html.indexOf("Fondo de Training");
    const about = html.indexOf("Acerca de");
    expect(own).toBeGreaterThan(0);
    expect(wallpaper).toBeGreaterThan(own);
    expect(about).toBeGreaterThan(wallpaper);
    expect(html).toMatch(/aria-pressed="true"[^>]*>.*Su color/);
    expect(html).toContain("Ajustes de arga");
  });

  it("el fondo se elige solo si hay fondo de app que elegir", () => {
    const html = renderToStaticMarkup(<AppSettings app={APP} />);
    expect(html).not.toContain("Fondo de Training");
    expect(html).toContain("Acerca de");
  });

  it("los de arga se abren desde su escritorio", () => {
    expect(ARGA_SETTINGS).toBe("/#ajustes");
  });
});
