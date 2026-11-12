import { DIPS, LAST_PRESS, LAST_SMITH, SQUAT } from "./fixtures";
import { describeSets, preferredVariant, prefill, shortDay, unusualLoad } from "./prefill";

describe("el chip preseleccionado", () => {
  it("es la última variante usada, no la primera del plan", () => {
    expect(preferredVariant(SQUAT, [LAST_SMITH, LAST_PRESS], [])).toBe("v-press");
  });

  it("sin histórico es la primera del plan", () => {
    expect(preferredVariant(SQUAT, [], [])).toBe("v-smith");
  });

  it("si hoy ya se empezó con una, es esa", () => {
    const today = [{ id: "e", plan_slot_id: SQUAT.id, variant_id: "v-smith", variant: "", position: 1, sets: [] }];
    expect(preferredVariant(SQUAT, [LAST_PRESS], today)).toBe("v-smith");
  });
});

describe("lo prellenado", () => {
  const smith = SQUAT.options[0];

  it("es la misma serie de la última vez", () => {
    expect(prefill(3, SQUAT, smith, LAST_SMITH, [])).toEqual({ load: 60, reps: 7 });
  });

  it("si hoy se hace una serie más que la última vez, repite la última que hubo", () => {
    expect(prefill(3, SQUAT, SQUAT.options[1], LAST_PRESS, [])).toEqual({ load: 140, reps: 9 });
  });

  it("sin histórico, la serie anterior de hoy; y sin nada, el mínimo del rango", () => {
    const today = [{ number: 1, reps: 9, weight: 50, added_load: null, completed: true, confirmed_at: "x" }];
    expect(prefill(2, SQUAT, smith, undefined, today)).toEqual({ load: 50, reps: 9 });
    expect(prefill(1, SQUAT, smith, undefined, [])).toEqual({ load: null, reps: 6 });
  });

  it("en peso corporal lo que se prellena es el lastre", () => {
    expect(prefill(1, DIPS, DIPS.options[0], undefined, [])).toEqual({ load: 0, reps: 8 });
  });
});

describe("cómo se leen las series", () => {
  it("con la misma carga se agrupan", () => {
    expect(describeSets(LAST_SMITH.sets, false)).toBe("8, 8, 7 × 60 kg");
  });

  it("si cambia la carga, cada una con la suya", () => {
    const sets = [
      { ...LAST_SMITH.sets[0]!, weight: 60 },
      { ...LAST_SMITH.sets[1]!, weight: 62.5, reps: 6 },
    ];
    expect(describeSets(sets, false)).toBe("8 × 60 kg · 6 × 62,5 kg");
    expect(describeSets([...LAST_SMITH.sets, { ...LAST_SMITH.sets[2]!, number: 4, weight: 65 }], false)).toBe(
      "8, 8, 7 × 60 kg · 7 × 65 kg",
    );
  });

  it("con lastre se suma, y sin lastre son solo reps", () => {
    const sets = [
      { number: 1, reps: 10, weight: null, added_load: 10, completed: true, confirmed_at: "x" },
      { number: 2, reps: 9, weight: null, added_load: 10, completed: true, confirmed_at: "x" },
    ];
    expect(describeSets(sets, true)).toBe("10, 9 + 10 kg");
    expect(describeSets(sets.map((set) => ({ ...set, added_load: null })), true)).toBe("10, 9");
  });

  it("el día va corto y sin punto", () => {
    expect(shortDay("2026-09-12")).toBe("12 sept");
  });
});

describe("el aviso de un peso raro", () => {
  const press = SQUAT.options[1];
  const here = { ...LAST_PRESS, gym_id: "g1" };

  it("salta si se aleja más de un 30 % de la última vez en esta máquina, y dice cuánto fue", () => {
    expect(unusualLoad({ load: 200, reps: 8 }, here, press, "g1")).toBe(140);
    expect(unusualLoad({ load: 90, reps: 8 }, here, press, "g1")).toBe(140);
  });

  it("no salta con lo de siempre ni con un salto normal", () => {
    expect(unusualLoad({ load: 140, reps: 10 }, here, press, "g1")).toBeNull();
    expect(unusualLoad({ load: 150, reps: 8 }, here, press, "g1")).toBeNull();
  });

  it("en otro centro es otra máquina, y no compara", () => {
    expect(unusualLoad({ load: 200, reps: 8 }, here, press, "g2")).toBeNull();
  });

  it("con lastre no salta: pasar de 10 a 20 kg es normal", () => {
    const dips = { ...here, sets: here.sets.map((set) => ({ ...set, weight: null, added_load: 10 })) };
    expect(unusualLoad({ load: 20, reps: 8 }, dips, DIPS.options[0], "g1")).toBeNull();
  });
});
