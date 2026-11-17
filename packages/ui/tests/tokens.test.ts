import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

const declared = (prefix: string): string[] => [
  ...new Set([...css.matchAll(new RegExp(`--${prefix}[a-z0-9-]*(?=\\s*:)`, "g"))].map((m) => m[0])),
];

describe("tokens.css is the only source of design values", () => {
  it("declares exactly three radii: surface, control and pill", () => {
    expect(declared("radius-").sort()).toEqual([
      "--radius-control",
      "--radius-pill",
      "--radius-surface",
    ]);
  });

  it("the spacing scale is closed and base 4, with the 2 px half step", () => {
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

  it("layers go bottom to top and none repeats", () => {
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

  it("three app widths: narrow, normal and wide", () => {
    expect(declared("app-width").sort()).toEqual([
      "--app-width",
      "--app-width-narrow",
      "--app-width-wide",
    ]);
  });

  it("declares the full scale and not one step more", () => {
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

  it("the old names keep their size", () => {
    expect(css).toMatch(/--text-caption:\s*0\.8125rem/);
    expect(css).toMatch(/--text-body:\s*1\.0625rem/);
    expect(css).toMatch(/--text-display:\s*2\.125rem/);
  });

  it("a KPI's figure has one step per place it fits", () => {
    expect(declared("text-kpi-").sort()).toEqual([
      "--text-kpi-l",
      "--text-kpi-m",
      "--text-kpi-s",
      "--text-kpi-xl",
    ]);
  });

  it("declares the four weights", () => {
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

  it("exposes the fixed palette of module tones", () => {
    expect(declared("hue-")).toHaveLength(8);
  });

  it("the tones stand out on the card in both themes: 3:1 at least", () => {
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

  it("secondary text is readable: --fg-faint at 4.5:1 over the card and the background, in both themes", () => {
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

  it("the calendar has ten tones, each solid, tinted and ink, in both themes", () => {
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

  it("an event reads in both themes: the bar at 3:1 and the title at 4.5:1", () => {
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

  it("icons have four sizes and a thick stroke, and no more", () => {
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

  it("the touch minimum is 44 px", () => {
    expect(css).toMatch(/--tap-target:\s*44px/);
  });
});

describe("card material", () => {
  it("`.surface` has no backdrop-filter", () => {
    const surface = css.slice(css.indexOf(".surface {"), css.indexOf(".surface::after"));
    expect(surface).not.toMatch(/backdrop-filter/);
  });

  it("shares radius and edge with the glass", () => {
    expect(css).toMatch(/\.surface\s*{[^}]*--radius-surface/);
    expect(css).toMatch(/\.surface::after/);
    expect(css).toMatch(/--surface-edge/);
  });

  it("turns opaque with prefers-reduced-transparency, like the glass", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-transparency: reduce)"));
    expect(reduced).toMatch(/--surface-opacity:\s*1/);
  });
});

describe("glass material", () => {
  it("--glass-opacity is a setting, not a constant buried in the component", () => {
    expect(css).toMatch(/--glass-opacity:/);
    expect(css).toMatch(/rgb\(var\(--glass-tint\) \/ var\(--glass-opacity\)\)/);
  });

  it("has a glass edge with a gradient", () => {
    expect(css).toMatch(/\.glass::after/);
    expect(css).toMatch(/--glass-edge-top/);
    expect(css).toMatch(/--glass-edge-bottom/);
  });

  it("honours prefers-reduced-transparency and prefers-reduced-motion", () => {
    expect(css).toMatch(/@media \(prefers-reduced-transparency: reduce\)/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });

  it("degrades the blur if the browser does not support backdrop-filter", () => {
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
  it("the three springs are springs, not ease curves", () => {
    for (const spring of ["--spring", "--spring-snappy", "--spring-bouncy"]) {
      expect(css).toMatch(new RegExp(`${spring}:\\s*linear\\(`));
    }
  });

  it("the bouncy spring overshoots 1 and the fast one barely does", () => {
    const overshoot = (name: string): number => {
      const body = css.match(new RegExp(`${name}:\\s*linear\\(([^)]*)\\)`, "s"))![1]!;
      return Math.max(...body.split(",").map((stop) => Number.parseFloat(stop)));
    };
    expect(overshoot("--spring-bouncy")).toBeGreaterThan(overshoot("--spring"));
    expect(overshoot("--spring")).toBeGreaterThan(overshoot("--spring-snappy"));
  });

  it("prefers-reduced-motion flattens every spring, not just the first", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const spring of ["--spring", "--spring-snappy", "--spring-bouncy"]) {
      expect(reduced).toMatch(new RegExp(`${spring}:\\s*linear\\(0,\\s*1\\)`));
    }
  });

  it("with reduced motion durations are short but not zero", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const duration of ["--duration-fast", "--duration-base", "--duration-slow"]) {
      expect(reduced).toMatch(new RegExp(`${duration}:\\s*1ms`));
    }
  });
});

describe("esquema oscuro", () => {
  it("redefines the background and glass tint under prefers-color-scheme", () => {
    const dark = block('@media (prefers-color-scheme: dark)');
    for (const token of ["--bg-base", "--fg", "--glass-tint", "--glass-opacity"]) {
      expect(dark).toContain(`${token}:`);
    }
  });

  it("the explicit dark theme is not empty", () => {
    expect(tokensIn(block('[data-theme="dark"]')).length).toBeGreaterThan(10);
  });

  it("the two dark blocks declare exactly the same tokens", () => {
    expect(tokensIn(block('[data-theme="dark"]'))).toEqual(
      tokensIn(block('@media (prefers-color-scheme: dark)')),
    );
  });
});

describe("each app's marks", () => {
  it("only arga has its own mark; apps share their icons' palette", () => {
    const brands = declared("brand-").map((name) => name.replace("--brand-", "").split("-")[0]);

    expect([...new Set(brands)]).toEqual(["arga"]);
    expect(declared("family-").sort()).toEqual(
      [
        "--family-calendar", "--family-companion", "--family-finance", "--family-goals",
        "--family-growth", "--family-health", "--family-system", "--family-wellbeing",
      ],
    );
  });

  it("arga's mark is the owner's choice: night blue on bone", () => {
    expect(css).toContain("--brand-arga-ground:  #e8e4db");
    expect(css).toContain("--brand-arga-river:   #2b3a4a");
    expect(css).toContain("--brand-arga-orchard: #4e7c63");
  });
});

describe("not one loose icon size", () => {
  it("the system stylesheets size icons with the four tokens", () => {
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
