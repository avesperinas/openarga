import { peek, reset } from "@openarga/app";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LastTime, Session, Today } from "./api";
import { DIPS, LAST_PRESS, LAST_SMITH, SESSION, SQUAT } from "./fixtures";
import { learnFrom, mergeHistory, offlineSession, readTodayKept, startAnywhere } from "./offline";
import { SyncQueue } from "./queue";

const TODAY: Today = {
  plan: {
    plan_id: "p",
    name: "PPL",
    version_id: "v",
    version: 1,
    valid_from: "2026-09-01",
    days: [{ id: "d-leg", name: "Leg", kind: "leg", position: 1, slots: [SQUAT, DIPS] }],
  },
  settings: { weekly_goal: 4, unit: "kg", default_increments: {} },
  next: { plan_day_id: "d-leg", name: "Leg", kind: "leg", rotation_number: 7, remaining: 3, days_in_rotation: 3 },
  in_progress: null,
  week: { done: 1, goal: 4, monday: "2026-09-14" },
};

describe("the last time, learnt", () => {
  it("keeps the most recent of each variant", () => {
    const older: LastTime = { ...LAST_SMITH, day: "2026-09-01" };
    expect(mergeHistory({ "v-smith": LAST_SMITH }, [older])["v-smith"]).toBe(LAST_SMITH);
    expect(mergeHistory({ "v-smith": older }, [LAST_SMITH])["v-smith"]).toBe(LAST_SMITH);
  });

  it("a finished session is the last time of what was done in it", () => {
    const finished: Session = {
      ...SESSION,
      ended_at: "2026-09-15T18:00:00Z",
      exercises: [{ id: "e", plan_slot_id: SQUAT.id, variant_id: "v-smith", variant: "", position: 1, sets: LAST_SMITH.sets }],
    };
    const learned = learnFrom(finished);
    expect(learned.find((entry) => entry.variant_id === "v-smith" && entry.day === "2026-09-15")).toBeDefined();
    expect(learnFrom(SESSION)).toEqual(SESSION.history);
  });
});

describe("the session of a workout started offline", () => {
  it("is the day of the kept plan, with the last time of its variants", () => {
    const session = offlineSession(TODAY, "s-new", undefined, new Date("2026-09-16T17:00:00Z"), {
      "v-smith": LAST_SMITH,
      "v-other": { ...LAST_PRESS, variant_id: "v-other" },
    });

    expect(session?.day_name).toBe("Leg");
    expect(session?.rotation_number).toBe(7);
    expect(session?.slots).toHaveLength(2);
    expect(session?.history.map((entry) => entry.variant_id)).toEqual(["v-smith"]);
    expect(session?.ended_at).toBeNull();
  });

  it("without that day in the kept plan it cannot", () => {
    expect(offlineSession(TODAY, "s", "d-push", new Date(), {})).toBeNull();
  });
});

describe("starting offline", () => {
  beforeEach(async () => {
    await reset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("with Today seen before, the session is painted and the queue creates it when the network is back", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify(TODAY), { status: 200 }));
    await readTodayKept();

    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    const queue = new SyncQueue({ storage: null, schedule: () => undefined });
    const id = await startAnywhere(undefined, queue, () => new Date("2026-09-16T17:00:00Z"), () => "s-new");

    expect(id).toBe("s-new");
    expect(peek<Session>("session:s-new")?.day_name).toBe("Leg");
    expect(peek<Today>("today")?.in_progress).toBe("s-new");
    expect(queue.pending("s-new")[0]).toMatchObject({
      key: "start:s-new",
      method: "PUT",
      path: "/sessions/s-new",
      body: { plan_day_id: "d-leg", started_at: "2026-09-16T17:00:00.000Z" },
    });
  });

  it("with nothing seen before, it says no", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(startAnywhere(undefined, new SyncQueue({ storage: null }))).rejects.toThrow();
  });
});
