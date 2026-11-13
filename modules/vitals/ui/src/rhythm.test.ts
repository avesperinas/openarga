import { describe, expect, it } from "vitest";

import type { Device, EcgTrace, Night } from "./api";
import { english, spanish } from "./i18n/testing";
import { ago, bandFigure, ecgSeries, irnFoot, wakeTiles } from "./rhythm";

const NOW = new Date("2026-10-20T18:00:00Z");

const band: Device = {
  id: "band",
  name: "Synthetic band",
  kind: "tracker",
  battery_pct: 82,
  battery: "high",
  last_sync: "2026-10-20T16:00:00Z",
};

describe("the band", () => {
  it("says its battery and when it synced", () => {
    expect(bandFigure(band, english, NOW)).toEqual({ value: "82 %", foot: "synced 2 h ago" });
  });

  it("warns with low battery or a day without syncing", () => {
    expect(bandFigure({ ...band, battery_pct: 15 }, english, NOW).tone).toBe("warning");
    expect(bandFigure({ ...band, last_sync: "2026-10-18T16:00:00Z" }, english, NOW)).toEqual({
      value: "82 %",
      foot: "synced 2 days ago",
      tone: "warning",
    });
  });

  it("without a percentage, it says the state", () => {
    expect(bandFigure({ ...band, battery_pct: null, battery: "medium" }, english, NOW).value).toBe("battery medium");
  });

  it("tells the time in words", () => {
    expect(ago("2026-10-20T17:55:00Z", english, NOW)).toBe("5 min ago");
  });
});

describe("the rhythm", () => {
  it("draws the trace with its second", () => {
    const trace = { step_seconds: 0.5, millivolts: [0, 0.1, -0.2] } as EcgTrace;

    expect(ecgSeries(trace, english, "en").labels).toEqual(["0 s", "0.5 s", "1 s"]);
    expect(ecgSeries(trace, spanish, "es").labels).toEqual(["0 s", "0,5 s", "1 s"]);
    expect(ecgSeries(trace, english, "en").series[0]?.values).toEqual([0, 0.1, -0.2]);
  });

  it("says how many alert windows were irregular", () => {
    const alert = { windows: 3, positive_windows: 2 } as Parameters<typeof irnFoot>[0];

    expect(irnFoot(alert, english)).toBe("2 of 3 windows with an irregular rhythm");
  });
});

describe("the awakenings", () => {
  it("only shows what is known", () => {
    const night = { awakenings: 12, minutes_out_of_bed: 4, minutes_after_wake_up: null } as Night;

    expect(wakeTiles(night, english)).toEqual([
      { label: "Awakenings", value: "12" },
      { label: "Out of bed", value: "4 min" },
    ]);
  });
});
