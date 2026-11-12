import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { RangeBar, rangeScale } from "../src/index";

describe("la barra con su zona objetivo", () => {
  it("deja sitio a lo comido y a la zona, y no se sale", () => {
    const scale = rangeScale(2200, 1900, 2100);
    expect(scale.value).toBeCloseTo(2200 / 2420);
    expect(scale.low).toBeCloseTo(1900 / 2420);
    expect(scale.high).toBeCloseTo(2100 / 2420);
    expect(rangeScale(50, 130).high).toBe(1);
  });

  it("dice cómo va a quien no ve los colores, y lo que no se sabe no es cero", () => {
    const html = renderToStaticMarkup(<RangeBar label="Fibra" value={12} unit="g" low={25} state="low" />);
    expect(html).toContain('aria-label="Fibra: 12 g, por debajo"');
    expect(html).toContain('data-state="low"');
    const unknown = renderToStaticMarkup(<RangeBar label="Vitamina D" value={null} unit="µg" low={15} />);
    expect(unknown).toContain("—");
    expect(unknown).not.toContain("range-bar-dot");
  });
});

