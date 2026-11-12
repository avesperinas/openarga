import { SESSION } from "./fixtures";
import type { Op } from "./queue";
import { madridTime, overlay, remap, restSince, sessionTimes } from "./session";

const queued: Op[] = [
  {
    key: "exercise:e1",
    session: "s1",
    method: "PUT",
    path: "/sessions/s1/exercises/e1",
    body: { variant_id: "v-press", plan_slot_id: "slot-squat" },
    attempts: 2,
  },
  {
    key: "set:e1:1",
    session: "s1",
    method: "PUT",
    path: "/sessions/s1/exercises/e1/sets/1",
    body: { reps: 10, weight: 140, added_load: null, completed: true, confirmed_at: "2026-09-15T17:05:00Z" },
    attempts: 1,
  },
];

describe("la sesión tras recargar", () => {
  it("lleva lo que el servidor no tiene todavía", () => {
    const [exercise] = overlay(SESSION, queued);

    expect(exercise?.variant).toBe("Prensa");
    expect(exercise?.sets.map((set) => [set.number, set.reps])).toEqual([[1, 10]]);
  });

  it("no mezcla la cola de otra sesión", () => {
    expect(overlay(SESSION, queued.map((op) => ({ ...op, session: "otra" })))).toEqual([]);
  });

  it("el descanso cuenta desde la última serie", () => {
    expect(restSince(overlay(SESSION, queued))).toBe("2026-09-15T17:05:00Z");
    expect(restSince([])).toBeNull();
  });

  it("reapuntar un ejercicio junta sus series con el que ya existía", () => {
    const mine = overlay(SESSION, queued);
    const theirs = [{ ...mine[0]!, id: "e2", sets: [{ ...mine[0]!.sets[0]!, number: 2 }] }];

    const merged = remap([...mine, ...theirs], "e1", "e2");

    expect(merged.map((exercise) => exercise.id)).toEqual(["e2"]);
    expect(merged[0]?.sets.map((set) => set.number)).toEqual([1, 2]);
  });
});

describe("la nota de un ejercicio", () => {
  it("tras recargar, la nota que no llegó al servidor sigue ahí", () => {
    const note: Op = {
      key: "notes:e1",
      session: "s1",
      method: "PUT",
      path: "/sessions/s1/exercises/e1/notes",
      body: { notes: "polea rara" },
      attempts: 1,
    };
    const [exercise] = overlay(SESSION, [...queued, note]);
    expect(exercise?.notes).toBe("polea rara");
  });
});

describe("las horas de un entreno terminado", () => {
  it("se leen en hora de Madrid", () => {
    expect(madridTime("2026-09-25T17:05:00Z")).toBe("19:05");
    expect(madridTime("2026-01-15T17:05:00Z")).toBe("18:05");
  });

  it("se mandan sin zona sobre el día de la sesión, con su duración", () => {
    expect(sessionTimes("2026-09-25", "19:05", "20:15")).toEqual({
      started_at: "2026-09-25T19:05:00",
      ended_at: "2026-09-25T20:15:00",
      seconds: 70 * 60,
    });
  });

  it("un fin antes del inicio es que cruzó la medianoche", () => {
    expect(sessionTimes("2026-09-30", "23:30", "00:40")).toEqual({
      started_at: "2026-09-30T23:30:00",
      ended_at: "2026-10-01T00:40:00",
      seconds: 70 * 60,
    });
  });

  it("sin una de las dos horas no hay nada que guardar", () => {
    expect(sessionTimes("2026-09-25", "", "20:15")).toBeNull();
  });
});
