import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

const declared = (prefix: string): string[] => [
  ...new Set([...css.matchAll(new RegExp(`--${prefix}[a-z0-9-]*(?=\\s*:)`, "g"))].map((m) => m[0])),
];

describe("tokens.css es la única fuente de valores de diseño", () => {
  it("declara exactamente tres radios: superficie, control y píldora", () => {
    expect(declared("radius-").sort()).toEqual([
      "--radius-control",
      "--radius-pill",
      "--radius-surface",
    ]);
  });

  it("la escala de espacio es cerrada y de base 4, con el medio paso de 2 px", () => {
    expect(declared("space-").sort()).toEqual([
      "--space-1",
      "--space-10",
      "--space-12",
      "--space-16",
      "--space-2",
      "--space-24",
      "--space-3",
      "--space-4",
      "--space-5",
      "--space-6",
      "--space-8",
      "--space-half",
    ]);
    for (const step of [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24]) {
      expect(css).toMatch(new RegExp(`--space-${step}: ${step / 4}rem;`));
    }
  });

  it("las capas van de abajo arriba y no se repite ninguna", () => {
    const order = [
      "--z-raised",
      "--z-sticky",
      "--z-nav",
      "--z-float",
      "--z-dropdown",
      "--z-modal",
      "--z-popover",
      "--z-toast",
      "--z-fullscreen",
    ];
    expect(declared("z-").sort()).toEqual([...order].sort());
    const values = order.map((name) => Number(new RegExp(`${name}:\\s*(-?\\d+);`).exec(css)?.[1]));
    expect(values).toEqual([...values].sort((a, b) => a - b));
    expect(new Set(values).size).toBe(values.length);
  });

  it("tres anchos de app: estrecho, normal y ancho", () => {
    expect(declared("app-width").sort()).toEqual([
      "--app-width",
      "--app-width-narrow",
      "--app-width-wide",
    ]);
  });

  it("declara la escala completa y ni un paso más", () => {
    expect(declared("text-").sort()).toEqual([
      "--text-body",
      "--text-callout",
      "--text-caption",
      "--text-caption1",
      "--text-caption2",
      "--text-display",
      "--text-footnote",
      "--text-headline",
      "--text-kpi-l",
      "--text-kpi-m",
      "--text-kpi-s",
      "--text-kpi-xl",
      "--text-subhead",
      "--text-title1",
      "--text-title2",
      "--text-title3",
    ]);
  });

  it("los nombres viejos conservan su tamaño", () => {
    expect(css).toMatch(/--text-caption:\s*0\.8125rem/);
    expect(css).toMatch(/--text-body:\s*1\.0625rem/);
    expect(css).toMatch(/--text-display:\s*2\.125rem/);
  });

  it("la cifra de un KPI tiene un paso por cada sitio donde cabe", () => {
    expect(declared("text-kpi-").sort()).toEqual([
      "--text-kpi-l",
      "--text-kpi-m",
      "--text-kpi-s",
      "--text-kpi-xl",
    ]);
  });

  it("declara los cuatro pesos", () => {
    expect(declared("weight-").sort()).toEqual([
      "--weight-bold",
      "--weight-medium",
      "--weight-regular",
      "--weight-semibold",
    ]);
  });

  it.each([
    "--font-sans",
    "--fg",
    "--fg-muted",
    "--accent",
    "--bg-base",
    "--bg-wash",
    "--numeric",
    "--spring",
  ])("declara %s", (token) => {
    expect(css).toContain(`${token}:`);
  });

  it("expone la paleta fija de tonos de módulo", () => {
    expect(declared("hue-")).toHaveLength(8);
  });

  it("los tonos se distinguen sobre la tarjeta en los dos temas: 3:1 como mínimo", () => {
    const hex = (block: string, name: string) =>
      new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`).exec(block)?.[1];
    const lum = (value: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => {
        const channel = parseInt(value.slice(i, i + 2), 16) / 255;
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    const ratio = (a: string, b: string) => {
      const [high, low] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (high! + 0.05) / (low! + 0.05);
    };
    const light = css.slice(0, css.indexOf("@media (prefers-color-scheme: dark)"));
    const dark = css.slice(css.indexOf(':root[data-theme="dark"]'));
    const cards = { light: "#ffffff", dark: "#1a202e" };

    for (let n = 1; n <= 8; n++) {
      const name = `hue-${n}`;
      const inLight = hex(light, name)!;
      const inDark = hex(dark, name) ?? inLight;
      expect(ratio(inLight, cards.light), `${name} en claro`).toBeGreaterThanOrEqual(3);
      expect(ratio(inDark, cards.dark), `${name} en oscuro`).toBeGreaterThanOrEqual(3);
    }
  });

  it("el texto secundario se lee: --fg-faint a 4,5:1 sobre la tarjeta y el fondo, en los dos temas", () => {
    const light = css.slice(0, css.indexOf("@media (prefers-color-scheme: dark)"));
    const dark = css.slice(css.indexOf(':root[data-theme="dark"]'));
    const hex = (text: string, name: string) =>
      new RegExp(`${name}:\\s*(#[0-9a-f]{6})`).exec(text)?.[1];
    const lum = (value: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => {
        const channel = parseInt(value.slice(i, i + 2), 16) / 255;
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    const ratio = (a: string, b: string) => {
      const [high, low] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (high! + 0.05) / (low! + 0.05);
    };
    const grounds = {
      light: [light, ["#ffffff", hex(light, "--bg-base")!]],
      dark: [dark, ["#1a202e", hex(dark, "--bg-base")!]],
    } as const;
    for (const [theme, [text, backs]] of Object.entries(grounds)) {
      for (const token of ["--fg-muted", "--fg-faint"]) {
        for (const back of backs) {
          expect(ratio(hex(text, token)!, back), `${token} sobre ${back} en ${theme}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
    expect(lum(hex(light, "--fg-faint")!)).toBeGreaterThan(lum(hex(light, "--fg-muted")!));
    expect(lum(hex(dark, "--fg-faint")!)).toBeLessThan(lum(hex(dark, "--fg-muted")!));
  });

  it("los tonos del calendario son diez, cada uno en pleno, tintado y tinta, en los dos temas", () => {
    const light = css.slice(0, css.indexOf("@media (prefers-color-scheme: dark)"));
    const expected = Array.from({ length: 10 }, (_, i) => [
      `--tone-${i + 1}`,
      `--tone-${i + 1}-ink`,
      `--tone-${i + 1}-soft`,
    ]).flat().sort();
    const tones = (block: string) => tokensIn(block).filter((name) => name.startsWith("--tone-"));
    expect(tones(light)).toEqual(expected);
    expect(tones(block('[data-theme="dark"]'))).toEqual(expected);
  });

  it("un evento se lee en los dos temas: la barra a 3:1 y el título a 4,5:1", () => {
    const hex = (block: string, name: string) =>
      new RegExp(`${name}:\\s*(#[0-9a-f]{6})`).exec(block)?.[1];
    const lum = (value: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => {
        const channel = parseInt(value.slice(i, i + 2), 16) / 255;
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    const ratio = (a: string, b: string) => {
      const [high, low] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (high! + 0.05) / (low! + 0.05);
    };
    const themes = {
      light: [css.slice(0, css.indexOf("@media (prefers-color-scheme: dark)")), "#ffffff"],
      dark: [css.slice(css.indexOf(':root[data-theme="dark"]')), "#1a202e"],
    } as const;
    for (const [theme, [text, card]] of Object.entries(themes)) {
      for (let n = 1; n <= 10; n++) {
        const tone = hex(text, `--tone-${n}`)!;
        const soft = hex(text, `--tone-${n}-soft`)!;
        const ink = hex(text, `--tone-${n}-ink`)!;
        expect(ratio(tone, card), `tono ${n} en ${theme}`).toBeGreaterThanOrEqual(3);
        expect(ratio(ink, soft), `título ${n} en ${theme}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("los iconos tienen cuatro tamaños y un trazo grueso, y no más", () => {
    expect(declared("icon-").sort()).toEqual([
      "--icon-badge",
      "--icon-badge-tint",
      "--icon-l",
      "--icon-m",
      "--icon-s",
      "--icon-stroke-bold",
      "--icon-xl",
    ]);
  });

  it.each([
    "--surface",
    "--surface-edge",
    "--separator",
    "--uncertain",
    "--scrim",
    "--focus-ring",
    "--fg-on-accent",
    "--elevation-drag",
    "--grid-gap",
    "--grid-columns-mobile",
    "--grid-columns-tablet",
    "--grid-columns-desktop",
    "--tap-target",
  ])("declara %s, que la pantalla necesita y no tenía", (token) => {
    expect(css).toContain(`${token}:`);
  });

  it("el mínimo táctil son 44 px", () => {
    expect(css).toMatch(/--tap-target:\s*44px/);
  });
});

describe("material de tarjeta", () => {
  it("`.surface` no lleva backdrop-filter", () => {
    const surface = css.slice(css.indexOf(".surface {"), css.indexOf(".surface::after"));
    expect(surface).not.toMatch(/backdrop-filter/);
  });

  it("comparte radio y canto con el cristal", () => {
    expect(css).toMatch(/\.surface\s*{[^}]*--radius-surface/);
    expect(css).toMatch(/\.surface::after/);
    expect(css).toMatch(/--surface-edge/);
  });

  it("sube a opaca con prefers-reduced-transparency, igual que el cristal", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-transparency: reduce)"));
    expect(reduced).toMatch(/--surface-opacity:\s*1/);
  });
});

describe("material de cristal", () => {
  it("--glass-opacity es un ajuste, no una constante enterrada en el componente", () => {
    expect(css).toMatch(/--glass-opacity:/);
    expect(css).toMatch(/rgb\(var\(--glass-tint\) \/ var\(--glass-opacity\)\)/);
  });

  it("tiene canto de vidrio con gradiente", () => {
    expect(css).toMatch(/\.glass::after/);
    expect(css).toMatch(/--glass-edge-top/);
    expect(css).toMatch(/--glass-edge-bottom/);
  });

  it("honra prefers-reduced-transparency y prefers-reduced-motion", () => {
    expect(css).toMatch(/@media \(prefers-reduced-transparency: reduce\)/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  it("degrada el blur si el navegador no soporta backdrop-filter", () => {
    expect(css).toMatch(/@supports \(backdrop-filter/);
  });
});

const block = (start: string): string => {
  const from = css.indexOf(start);
  return css.slice(from, css.indexOf("}", css.indexOf("{", from)));
};

const tokensIn = (text: string): string[] =>
  [...new Set([...text.matchAll(/--[a-z0-9-]+(?=\s*:)/g)].map((m) => m[0]))].sort();

describe("movimiento", () => {
  it("los tres muelles son muelles, no curvas de ease", () => {
    for (const spring of ["--spring", "--spring-snappy", "--spring-bouncy"]) {
      expect(css).toMatch(new RegExp(`${spring}:\\s*linear\\(`));
    }
  });

  it("el muelle con rebote se pasa de 1 y el rápido casi no", () => {
    const overshoot = (name: string): number => {
      const body = css.match(new RegExp(`${name}:\\s*linear\\(([^)]*)\\)`, "s"))![1]!;
      return Math.max(...body.split(",").map((stop) => Number.parseFloat(stop)));
    };
    expect(overshoot("--spring-bouncy")).toBeGreaterThan(overshoot("--spring"));
    expect(overshoot("--spring")).toBeGreaterThan(overshoot("--spring-snappy"));
  });

  it("prefers-reduced-motion aplana todos los muelles, no solo el primero", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const spring of ["--spring", "--spring-snappy", "--spring-bouncy"]) {
      expect(reduced).toMatch(new RegExp(`${spring}:\\s*linear\\(0,\\s*1\\)`));
    }
  });

  it("con movimiento reducido las duraciones son cortas pero no cero", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const duration of ["--duration-fast", "--duration-base", "--duration-slow"]) {
      expect(reduced).toMatch(new RegExp(`${duration}:\\s*1ms`));
    }
  });
});

describe("esquema oscuro", () => {
  it("redefine el fondo y el tinte de cristal bajo prefers-color-scheme", () => {
    const dark = block('@media (prefers-color-scheme: dark)');
    for (const token of ["--bg-base", "--fg", "--glass-tint", "--glass-opacity"]) {
      expect(dark).toContain(`${token}:`);
    }
  });

  it("el tema oscuro explícito no está vacío", () => {
    expect(tokensIn(block('[data-theme="dark"]')).length).toBeGreaterThan(10);
  });

  it("los dos bloques oscuros declaran exactamente los mismos tokens", () => {
    expect(tokensIn(block('[data-theme="dark"]'))).toEqual(
      tokensIn(block('@media (prefers-color-scheme: dark)')),
    );
  });
});

describe("las marcas de cada app", () => {
  it("solo arga tiene marca propia; las apps comparten la paleta de sus iconos", () => {
    const brands = declared("brand-").map((name) => name.replace("--brand-", "").split("-")[0]);

    expect([...new Set(brands)]).toEqual(["arga"]);
    expect(declared("family-").sort()).toEqual(
      [
        "--family-calendar", "--family-companion", "--family-finance", "--family-goals",
        "--family-growth", "--family-health", "--family-system", "--family-wellbeing",
      ],
    );
  });

  it("la marca de arga es la que eligió el dueño: azul noche sobre hueso", () => {
    expect(css).toContain("--brand-arga-ground:  #e8e4db");
    expect(css).toContain("--brand-arga-river:   #2b3a4a");
    expect(css).toContain("--brand-arga-orchard: #4e7c63");
  });
});

describe("ni un tamaño de icono suelto", () => {
  it("las hojas del sistema dimensionan los iconos con los cuatro tokens", () => {
    for (const sheet of ["../controls.css", "../library.css", "../widget.css"]) {
      const source = readFileSync(new URL(sheet, import.meta.url), "utf8");
      const rules = source.match(/\.icon[^{]*\{[^}]*\}/g) ?? [];
      for (const rule of rules) {
        expect(rule, sheet).not.toMatch(/(?:width|height):\s*\d+px/);
        expect(rule, sheet).not.toMatch(/stroke-width:\s*[\d.]+;/);
      }
    }
  });
});
