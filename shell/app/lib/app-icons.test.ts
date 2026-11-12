import { describe, expect, it } from "vitest";

import { appIconOf, appIcons } from "./app-icons";
import type { ModuleSummary } from "./kernel";

const vitals = { id: "vitals", name: "Vitals", view: "/vitals", updated_at: "2026-11-01T10:00:00Z" } as ModuleSummary;

describe("los iconos de las apps", () => {
  it("la firma de cada tarjeta va en el acabado elegido (ADR-0170)", () => {
    const at = Date.parse(vitals.updated_at);
    expect(appIconOf(vitals)).toBe(`/vitals/icon.svg?v=${at}`);
    expect(appIcons([vitals], "paper")).toEqual({ vitals: `/vitals/icon-paper.svg?v=${at}` });
    expect(appIcons([vitals])).toEqual({ vitals: `/vitals/icon.svg?v=${at}` });
  });
});
