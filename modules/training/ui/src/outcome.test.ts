import type { LastTime, LoggedSet } from "./api";
import { bestSet, compare } from "./outcome";

const set = (number: number, reps: number, weight: number | null, added_load: number | null = null): LoggedSet => ({
  number,
  reps,
  weight,
  added_load,
  completed: true,
  confirmed_at: "2026-09-14T17:00:00Z",
});

const last = (day: string, ...sets: LoggedSet[]): LastTime => ({ variant_id: "v", day, sets });
const DAY = "2026-09-14";
const BEFORE = "2026-09-07";

describe("la mejor serie", () => {
  it("es la de más fuerza estimada, no la de más kilos", () => {
    expect(bestSet([set(1, 10, 60), set(2, 3, 65)], false)?.number).toBe(1);
  });

  it("no cuenta las que no se hicieron", () => {
    expect(bestSet([{ ...set(1, 8, 100), completed: false }, set(2, 8, 60)], false)?.number).toBe(2);
  });

  it("sin carga, con peso corporal, es la de más reps", () => {
    expect(bestSet([set(1, 8, null), set(2, 10, null)], true)?.number).toBe(2);
  });
});

describe("contra la vez anterior", () => {
  it("con la misma carga dice las reps", () => {
    expect(compare([set(1, 9, 60)], last(BEFORE, set(1, 8, 60)), false, DAY)).toEqual({ text: "+1 rep", direction: "up" });
  });

  it("con otra carga dice los kilos", () => {
    expect(compare([set(1, 8, 62.5)], last(BEFORE, set(1, 8, 60)), false, DAY)).toEqual({ text: "+2,5 kg", direction: "up" });
  });

  it("si subir kilos costó demasiadas reps, baja aunque los kilos suban", () => {
    expect(compare([set(1, 4, 62.5)], last(BEFORE, set(1, 10, 60)), false, DAY)).toEqual({
      text: "+2,5 kg",
      direction: "down",
    });
  });

  it("lo mismo es igual", () => {
    expect(compare([set(1, 8, 60)], last(BEFORE, set(1, 8, 60)), false, DAY)?.direction).toBe("flat");
  });

  it("con lastre compara el lastre", () => {
    expect(compare([set(1, 6, null, 15)], last(BEFORE, set(1, 6, null, 10)), true, DAY)?.text).toBe("+5 kg");
  });

  it("sin vez anterior, o con una posterior, es la primera vez", () => {
    expect(compare([set(1, 8, 60)], undefined, false, DAY)?.direction).toBe("first");
    expect(compare([set(1, 8, 60)], last("2026-09-21", set(1, 8, 50)), false, DAY)?.direction).toBe("first");
  });

  it("sin series hechas no hay nada que comparar", () => {
    expect(compare([], last(BEFORE, set(1, 8, 60)), false, DAY)).toBeNull();
  });
});
