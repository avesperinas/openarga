import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BodyWeightCard, weighedOn, weightChange } from "../src/index";

const days = [
  { day: "2026-08-20", kg: 81.2 },
  { day: "2026-09-10", kg: 80.6 },
  { day: "2026-09-24", kg: 80.4 },
];

describe("el peso corporal", () => {
  it("dice cuándo fue la última pesada como se diría", () => {
    expect(weighedOn("2026-09-24", "2026-09-24")).toBe("hoy");
    expect(weighedOn("2026-09-23", "2026-09-24")).toBe("ayer");
    expect(weighedOn("2026-09-10", "2026-09-24")).toBe("10 sept");
  });

  it("compara con el peso de hace un mes, si lo hay cerca", () => {
    expect(weightChange(days)).toBe(-0.8);
    expect(weightChange(days.slice(1))).toBeNull();
    expect(weightChange([])).toBeNull();
    expect(weightChange([{ day: "2025-01-01", kg: 90 }, { day: "2026-09-24", kg: 80 }])).toBeNull();
  });

  it("enseña la cifra, el cambio, la línea y cómo apuntarlo", () => {
    const html = renderToStaticMarkup(
      <BodyWeightCard history={{ days, latest: days[2]! }} today="2026-09-24" onLog={() => undefined} />,
    );

    expect(html).toContain("80,4");
    expect(html).toContain("hoy · −0,8 kg en 30 días");
    expect(html).toContain("trend-chart");
    expect(html).toContain("Apuntar");
    expect(html).toContain("El mismo peso en Salud, Macros y Training.");
  });

  it("sin pesos lo dice, y lo pendiente de llegar también", () => {
    const empty = renderToStaticMarkup(<BodyWeightCard history={{ days: [], latest: null }} onLog={() => undefined} />);
    const pending = renderToStaticMarkup(
      <BodyWeightCard history={{ days: days.slice(2), latest: days[2]!, pending: true }} today="2026-09-24" onLog={() => undefined} />,
    );

    expect(empty).toContain("Aún no hay ningún peso apuntado.");
    expect(empty).not.toContain("trend-chart");
    expect(pending).toContain("Llegará a Salud en cuanto conteste.");
  });
});
