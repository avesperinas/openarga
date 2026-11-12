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
  it("llegar desde el escritorio deja ofrecer la vuelta", () => {
    expect(cameFromArga("recipes", `${ORIGIN}/`, ORIGIN, storage())).toBe(true);
  });

  it("y se recuerda al navegar dentro de la app, donde ya no hay referrer que lo diga", () => {
    const remembered = storage();
    cameFromArga("recipes", `${ORIGIN}/`, ORIGIN, remembered);

    expect(cameFromArga("recipes", "", ORIGIN, remembered)).toBe(true);
  });

  it("cada app recuerda lo suyo: venir a Training no ofrece volver desde Money", () => {
    const remembered = storage();
    cameFromArga("training", `${ORIGIN}/`, ORIGIN, remembered);

    expect(cameFromArga("money", "", ORIGIN, remembered)).toBe(false);
  });

  it("abriendo la app instalada no hay de dónde volver", () => {
    expect(cameFromArga("recipes", "", ORIGIN, storage())).toBe(false);
  });

  it("venir de otro sitio de la misma app no es venir de arga", () => {
    expect(cameFromArga("recipes", `${ORIGIN}/recipes/receta/a1`, ORIGIN, storage())).toBe(
      false,
    );
  });

  it("y venir de fuera del hostname, tampoco", () => {
    expect(cameFromArga("recipes", "https://otro.example/", ORIGIN, storage())).toBe(false);
  });

  it("sin almacenamiento (modo privado) no revienta: simplemente no se ofrece", () => {
    expect(cameFromArga("recipes", "", ORIGIN, null)).toBe(false);
  });
});

describe("la cabecera de una app", () => {
  it("lleva la marca de la app, el antetítulo y el título, con la forma de todas", () => {
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

  it("una pantalla que cuelga de otra lleva un atrás con su nombre, que no es la salida a arga", () => {
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

  it("sin pantalla de la que colgar no hay atrás", () => {
    const html = renderToStaticMarkup(
      <AppHeader app={{ id: "money", name: "Money", icon: "/money/icon.svg?v=1" }} title="Resumen" />,
    );

    expect(html).not.toContain("app-back");
  });
});

describe("el fondo de una app", () => {
  it("sin foto ni velo: el tinte de su color, y la clase de la app para sus estilos", () => {
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

  it("con `colored`, las piezas del sistema toman el color de la app", () => {
    const html = renderToStaticMarkup(
      <AppBackdrop app="library" className="library-desktop" colored>
        <p>dentro</p>
      </AppBackdrop>,
    );

    expect(html).toContain('data-kind="hue-5"');
  });

  it("lo elegido en sus Ajustes manda, y lo que ya no existe vuelve a su color", () => {
    expect(backgroundOf("training", { app_backgrounds: { training: "plain" } })).toBe("plain");
    expect(backgroundOf("training", { app_backgrounds: { training: "hue-2" } })).toBe("hue-2");
    expect(backgroundOf("training", { app_backgrounds: { training: "foto" as never } })).toBe("app");
    expect(backgroundOf("training", { app_wallpapers: { training: "duna" } })).toBe("app");
    expect(backgroundStyle("training", "plain")).toEqual({});
    expect(backgroundStyle("training", "hue-2")).toEqual({ "--app-background-hue": "var(--hue-2)" });
  });

  it("el color de cada app es el de su manifiesto", () => {
    const root = resolve(__dirname, "../../../modules");
    for (const id of readdirSync(root)) {
      const file = resolve(root, id, "manifest.yaml");
      if (id.startsWith("_") || !existsSync(file)) continue;
      const hue = /^ {2}hue: (\d+)$/m.exec(readFileSync(file, "utf8"))?.[1];
      expect([id, APP_HUES[id]]).toEqual([id, hue ? Number(hue) : undefined]);
    }
  });
});
