import { ApiError, type Today } from "./api";
import { resolveNext, startNext } from "./Next";

const BASE: Today = {
  plan: null,
  settings: { weekly_goal: 5, unit: "kg", default_increments: {} },
  next: { plan_day_id: "d", name: "Pull", kind: "pull", rotation_number: 3, remaining: 2, days_in_rotation: 3 },
  in_progress: null,
  week: { done: 2, goal: 5, monday: "2026-09-14" },
};

describe("el widget de siguiente entreno", () => {
  it("sin entreno a medias, pide confirmar el que toca y no empieza nada", async () => {
    expect(await resolveNext(async () => BASE)).toEqual({ confirm: BASE.next });
  });

  it("con uno a medias, abre ese sin preguntar", async () => {
    expect(await resolveNext(async () => ({ ...BASE, in_progress: "a-medias" }))).toEqual({ session: "a-medias" });
  });

  it("sin plan, a Hoy", async () => {
    expect(await resolveNext(async () => ({ ...BASE, next: null }))).toEqual({ today: true });
  });

  it("confirmado, empieza y abre el nuevo", async () => {
    let started = 0;
    const id = await startNext(
      async () => BASE,
      async () => {
        started += 1;
        return "nueva";
      },
    );
    expect(id).toBe("nueva");
    expect(started).toBe(1);
  });

  it("si otro dispositivo lo empezó a la vez, abre ese", async () => {
    const id = await startNext(
      async () => ({ ...BASE, in_progress: "del-otro" }),
      async () => {
        throw new ApiError(409, "ya hay una sesión en curso");
      },
    );
    expect(id).toBe("del-otro");
  });
});
