import { describe, expect, it } from "vitest";

import { envelopeKey, missing, parseEnvelopeKey, stale } from "./envelope";

const item = (widget: string, option?: string) => ({ source: "vitals", widget, ...(option ? { option } : {}) });

describe("what the screen requests on its own (T-V06)", () => {
  it("is what did not arrive with the page, once per envelope", () => {
    const placed = [item("steps"), item("sleep"), item("sleep"), item("balance", "cuenta-a")];

    expect(missing(placed, { "vitals/steps": null })).toEqual([
      item("sleep"),
      item("balance", "cuenta-a"),
    ]);
  });

  it("an envelope that arrived in error is not requested again by itself: Try again does", () => {
    expect(missing([item("steps")], { "vitals/steps": null })).toEqual([]);
  });
});

describe("what needs repainting (T-V07)", () => {
  const refresh: Record<string, number> = { "vitals/steps": 60, "money/summary": 3600 };
  const of = (key: string) => refresh[parseEnvelopeKey(key).widget];

  it("is what has been on screen longer than its refresh, or five minutes if it says none", () => {
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

  it("nothing goes more than five minutes without a request, even if its manifest says an hour", () => {
    const now = 10_000_000;
    expect(stale(["money/summary"], of, { "money/summary": now - 299_000 }, now)).toEqual([]);
    expect(stale(["money/summary"], of, { "money/summary": now - 300_000 }, now)).toEqual(["money/summary"]);
  });

  it("what has not arrived yet is not repainted: whoever asks for what is missing asks for it", () => {
    expect(stale(["vitals/steps"], of, {}, 1_000_000)).toEqual([]);
  });

  it("a key with a choice splits back into its parts", () => {
    expect(parseEnvelopeKey(envelopeKey("money", "balance", "cuenta-a"))).toEqual({
      widget: "money/balance",
      option: "cuenta-a",
    });
    expect(parseEnvelopeKey("vitals/steps")).toEqual({ widget: "vitals/steps", option: null });
  });
});
