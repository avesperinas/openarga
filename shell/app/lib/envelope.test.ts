import { describe, expect, it } from "vitest";

import { envelopeKey, missing, parseEnvelopeKey, stale } from "./envelope";

const item = (widget: string, option?: string) => ({ source: "vitals", widget, ...(option ? { option } : {}) });

describe("lo que la pantalla pide por su cuenta (T-V06)", () => {
  it("es lo que no llegó con la página, una vez por sobre", () => {
    const placed = [item("steps"), item("sleep"), item("sleep"), item("balance", "cuenta-a")];

    expect(missing(placed, { "vitals/steps": null })).toEqual([
      item("sleep"),
      item("balance", "cuenta-a"),
    ]);
  });

  it("un sobre que llegó en error no se vuelve a pedir solo: lo pide Reintentar", () => {
    expect(missing([item("steps")], { "vitals/steps": null })).toEqual([]);
  });
});

describe("lo que toca repintar (T-V07)", () => {
  const refresh: Record<string, number> = { "vitals/steps": 60, "money/summary": 3600 };
  const of = (key: string) => refresh[parseEnvelopeKey(key).widget];

  it("es lo que lleva en pantalla más que su refresco, o cinco minutos si no dice", () => {
    const now = 1_000_000;
    const fetched = {
      "vitals/steps": now - 61_000,
      "vitals/sleep": now - 299_000,
      "money/balance?cuenta-a": now - 301_000,
    };

    expect(stale(Object.keys(fetched), of, fetched, now)).toEqual([
      "vitals/steps",
      "money/balance?cuenta-a",
    ]);
  });

  it("nada pasa más de cinco minutos sin pedirse, aunque su manifiesto diga una hora", () => {
    const now = 10_000_000;
    expect(stale(["money/summary"], of, { "money/summary": now - 299_000 }, now)).toEqual([]);
    expect(stale(["money/summary"], of, { "money/summary": now - 300_000 }, now)).toEqual(["money/summary"]);
  });

  it("lo que aún no ha llegado no se repinta: lo pide quien pide lo que falta", () => {
    expect(stale(["vitals/steps"], of, {}, 1_000_000)).toEqual([]);
  });

  it("una clave con elección vuelve a sus partes", () => {
    expect(parseEnvelopeKey(envelopeKey("money", "balance", "cuenta-a"))).toEqual({
      widget: "money/balance",
      option: "cuenta-a",
    });
    expect(parseEnvelopeKey("vitals/steps")).toEqual({ widget: "vitals/steps", option: null });
  });
});
