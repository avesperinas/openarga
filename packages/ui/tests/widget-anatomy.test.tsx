import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { Widget, WidgetBars, whenLabel } from "../src/index";

const NOW = new Date(2026, 8, 28, 10, 0);
const at = (days: number, hour = 9, minute = 30) =>
  new Date(2026, 8, 28 + days, hour, minute);

describe("cuándo es lo siguiente", () => {
  it("dice el día y no solo la hora", () => {
    expect(whenLabel(at(0), NOW)).toBe("09:30");
    expect(whenLabel(at(1), NOW)).toBe("Mañana, 09:30");
    expect(whenLabel(at(3), NOW)).toBe("Jueves, 09:30");
    expect(whenLabel(at(-1), NOW)).toBe("Ayer, 09:30");
    expect(whenLabel(at(9), NOW)).toMatch(/^7 oct/);
  });

  it("un día entero no lleva hora, y otro año lleva el año", () => {
    expect(whenLabel(at(1, 0, 0), NOW)).toBe("Mañana");
    expect(whenLabel(new Date(2027, 1, 3, 0, 0), NOW)).toMatch(/2027/);
  });
});

describe("las etiquetas de unas barras", () => {
  const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep"];
  const series = months.map((_, index) => index + 1);

  it("en una tarjeta estrecha se quedan en la primera, la última y la resaltada", () => {
    const html = renderToStaticMarkup(
      <Widget title="Páginas" hue={5} size="2x2" shape="number" state="ready">
        <WidgetBars series={series} labels={months} highlight={4} />
      </Widget>,
    );
    expect(html).toContain(">ene<");
    expect(html).toContain(">may<");
    expect(html).toContain(">sep<");
    expect(html).not.toContain(">feb<");
  });

  it("fuera de una tarjeta van todas: la pantalla de una app tiene el ancho que tiene", () => {
    const html = renderToStaticMarkup(<WidgetBars series={series} labels={months} />);
    for (const month of months) expect(html).toContain(`>${month}<`);
  });
});
