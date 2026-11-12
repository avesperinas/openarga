import { describe, expect, it } from "vitest";

import type { Device, EcgTrace, Night } from "./api";
import { ago, bandFigure, ecgSeries, irnFoot, wakeTiles } from "./rhythm";

const NOW = new Date("2026-10-20T18:00:00Z");

const band: Device = {
  id: "band",
  name: "Pulsera sintética",
  kind: "tracker",
  battery_pct: 82,
  battery: "high",
  last_sync: "2026-10-20T16:00:00Z",
};

describe("la pulsera", () => {
  it("dice su batería y cuándo sincronizó", () => {
    expect(bandFigure(band, NOW)).toEqual({ value: "82 %", foot: "sincronizó hace 2 h" });
  });

  it("avisa con la batería baja o un día sin sincronizar", () => {
    expect(bandFigure({ ...band, battery_pct: 15 }, NOW).tone).toBe("warning");
    expect(bandFigure({ ...band, last_sync: "2026-10-18T16:00:00Z" }, NOW)).toEqual({
      value: "82 %",
      foot: "sincronizó hace 2 días",
      tone: "warning",
    });
  });

  it("sin porcentaje, dice el estado", () => {
    expect(bandFigure({ ...band, battery_pct: null, battery: "medium" }, NOW).value).toBe("batería media");
  });

  it("cuenta el tiempo en palabras", () => {
    expect(ago("2026-10-20T17:55:00Z", NOW)).toBe("hace 5 min");
  });
});

describe("el ritmo", () => {
  it("pinta la traza con su segundo", () => {
    const trace = { step_seconds: 0.5, millivolts: [0, 0.1, -0.2] } as EcgTrace;

    expect(ecgSeries(trace).labels).toEqual(["0 s", "0,5 s", "1 s"]);
    expect(ecgSeries(trace).series[0]?.values).toEqual([0, 0.1, -0.2]);
  });

  it("dice cuántas ventanas del aviso dieron irregular", () => {
    const alert = { windows: 3, positive_windows: 2 } as Parameters<typeof irnFoot>[0];

    expect(irnFoot(alert)).toBe("2 de 3 ventanas con ritmo irregular");
  });
});

describe("los despertares", () => {
  it("solo enseña lo que se sabe", () => {
    const night = { awakenings: 12, minutes_out_of_bed: 4, minutes_after_wake_up: null } as Night;

    expect(wakeTiles(night)).toEqual([
      { label: "Despertares", value: "12" },
      { label: "Levantado", value: "4 min" },
    ]);
  });
});
