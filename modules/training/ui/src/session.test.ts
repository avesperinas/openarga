import { SESSION } from "./fixtures";
import type { Op } from "./queue";
import { localTime, overlay, remap, restSince, sessionTimes } from "./session";

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

describe("the session after reloading", () => {
  it("carries what the server does not have yet", () => {
    const [exercise] = overlay(SESSION, queued);

    expect(exercise?.variant).toBe("Leg press");
    expect(exercise?.sets.map((set) => [set.number, set.reps])).toEqual([[1, 10]]);
  });

  it("does not mix the queue of another session", () => {
    expect(overlay(SESSION, queued.map((op) => ({ ...op, session: "other" })))).toEqual([]);
  });

  it("rest counts from the last set", () => {
    expect(restSince(overlay(SESSION, queued))).toBe("2026-09-15T17:05:00Z");
    expect(restSince([])).toBeNull();
  });

  it("re-pointing an exercise joins its sets with the one that already existed", () => {
    const mine = overlay(SESSION, queued);
    const theirs = [{ ...mine[0]!, id: "e2", sets: [{ ...mine[0]!.sets[0]!, number: 2 }] }];

    const merged = remap([...mine, ...theirs], "e1", "e2");

    expect(merged.map((exercise) => exercise.id)).toEqual(["e2"]);
    expect(merged[0]?.sets.map((set) => set.number)).toEqual([1, 2]);
  });
});

describe("the note of an exercise", () => {
  it("after reloading, the note that did not reach the server is still there", () => {
    const note: Op = {
      key: "notes:e1",
      session: "s1",
      method: "PUT",
      path: "/sessions/s1/exercises/e1/notes",
      body: { notes: "odd cable" },
      attempts: 1,
    };
    const [exercise] = overlay(SESSION, [...queued, note]);
    expect(exercise?.notes).toBe("odd cable");
  });
});

describe("the times of a finished workout", () => {
  it("read in the time zone of the person", () => {
    expect(localTime("2026-09-25T17:05:00Z", "Europe/Madrid", "en")).toBe("19:05");
    expect(localTime("2026-01-15T17:05:00Z", "Europe/Madrid", "en")).toBe("18:05");
    expect(localTime("2026-09-25T17:05:00Z", "America/New_York", "es")).toBe("13:05");
  });

  it("are sent without zone on the day of the session, with its duration", () => {
    expect(sessionTimes("2026-09-25", "19:05", "20:15")).toEqual({
      started_at: "2026-09-25T19:05:00",
      ended_at: "2026-09-25T20:15:00",
      seconds: 70 * 60,
    });
  });

  it("an end before the start means it crossed midnight", () => {
    expect(sessionTimes("2026-09-30", "23:30", "00:40")).toEqual({
      started_at: "2026-09-30T23:30:00",
      ended_at: "2026-10-01T00:40:00",
      seconds: 70 * 60,
    });
  });

  it("without one of the two times there is nothing to save", () => {
    expect(sessionTimes("2026-09-25", "", "20:15")).toBeNull();
  });
});
