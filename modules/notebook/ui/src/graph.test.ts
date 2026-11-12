import { describe, expect, it } from "vitest";

import { toneIndex } from "./GraphView";

describe("el color de una carpeta", () => {
  it("es el mismo siempre, sin distinguir mayúsculas, y la raíz no tiene", () => {
    expect(toneIndex("Study/Alemán", 10)).toBe(toneIndex("study/alemán", 10));
    expect(toneIndex("Study/Alemán", 10)).toBeGreaterThanOrEqual(0);
    expect(toneIndex("Study/Alemán", 10)).toBeLessThan(10);
    expect(toneIndex("", 10)).toBe(-1);
  });
});
