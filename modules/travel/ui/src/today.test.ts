import { describe, expect, it } from "vitest";

import type { TodayEntry } from "./api";
import { clock, onApple, progress } from "./today";

const entry = (title: string, starts: string | null, ends: string | null = null): TodayEntry => ({
  type: "block",
  id: title,
  title,
  detail: null,
  kind: "activity",
  starts_at: starts,
  ends_at: ends,
  where: null,
  confirmation: null,
});

describe("hoy", () => {
  const day = [entry("Sales", "11:00:00"), entry("Paseo", null), entry("Tren", "12:05:00", "13:00:00"), entry("Cena", "20:30")];

  it("lo que pasó está hecho, y lo de antes también; lo siguiente es lo primero que queda", () => {
    expect(progress(day, "12:30")).toEqual({ done: [true, true, false, false], next: 2 });
    expect(progress(day, "13:00")).toEqual({ done: [true, true, true, false], next: 3 });
    expect(progress(day, "08:00")).toEqual({ done: [false, false, false, false], next: 0 });
    expect(progress(day, "23:00").next).toBeNull();
  });

  it("la hora es la del dispositivo y el mapa, el del teléfono", () => {
    expect(clock(new Date(2027, 3, 2, 9, 5))).toEqual({ day: "2027-04-02", time: "09:05" });
    expect(onApple("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)", 5)).toBe(true);
    expect(onApple("Mozilla/5.0 (Linux; Android 15)", 5)).toBe(false);
  });
});
