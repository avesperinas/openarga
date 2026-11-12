import { ApiError, type Today } from "./api";
import { resolveNext, startNext } from "./Next";

const BASE: Today = {
  plan: null,
  settings: { weekly_goal: 5, unit: "kg", default_increments: {} },
  next: { plan_day_id: "d", name: "Pull", kind: "pull", rotation_number: 3, remaining: 2, days_in_rotation: 3 },
  in_progress: null,
  week: { done: 2, goal: 5, monday: "2026-09-14" },
};

describe("the next workout widget", () => {
  it("without a workout half done, asks to confirm the due one and starts nothing", async () => {
    expect(await resolveNext(async () => BASE)).toEqual({ confirm: BASE.next });
  });

  it("with one half done, opens it without asking", async () => {
    expect(await resolveNext(async () => ({ ...BASE, in_progress: "half-done" }))).toEqual({ session: "half-done" });
  });

  it("without a plan, to Today", async () => {
    expect(await resolveNext(async () => ({ ...BASE, next: null }))).toEqual({ today: true });
  });

  it("confirmed, starts and opens the new one", async () => {
    let started = 0;
    const id = await startNext(
      async () => BASE,
      async () => {
        started += 1;
        return "new";
      },
    );
    expect(id).toBe("new");
    expect(started).toBe(1);
  });

  it("if another device started it at the same time, opens that one", async () => {
    const id = await startNext(
      async () => ({ ...BASE, in_progress: "from-the-other" }),
      async () => {
        throw new ApiError(409, "there is already a session in progress");
      },
    );
    expect(id).toBe("from-the-other");
  });
});
