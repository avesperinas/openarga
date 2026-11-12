import { describe, expect, it } from "vitest";

import { daySentence, daysStarted, moveVerdict, pace, recoveryLine, recoveryVerdict, sleepVerdict, trainVerdict, weekDots } from "./today";

describe("el ritmo de la semana, a estas alturas", () => {
  it("un jueves se compara con cuatro séptimos de la media, no con la semana entera", () => {
    const thursday = new Date("2026-11-05T12:00:00");
    expect(daysStarted(thursday)).toBe(4);
    expect(pace(240, 520, thursday)).toBeCloseTo(240 / ((520 * 4) / 7));
    expect(trainVerdict(pace(240, 520, thursday))).toEqual({ verdict: "Algo por debajo", tone: "neutral" });
  });

  it("el lunes cuenta un día y el domingo siete", () => {
    expect(daysStarted(new Date("2026-11-02T12:00:00"))).toBe(1);
    expect(daysStarted(new Date("2026-11-08T12:00:00"))).toBe(7);
    expect(pace(520, 520, new Date("2026-11-08T12:00:00"))).toBe(1);
  });

  it("sin media, no hay ritmo", () => {
    expect(pace(100, null, new Date())).toBeNull();
    expect(trainVerdict(null).verdict).toBe("Sin media aún");
  });
});

describe("las palabras de Hoy", () => {
  it("el sueño por su calidad y cómo llegas, con 50 lo de siempre", () => {
    expect(sleepVerdict({ value: 81, quality: "good", duration: 40, depth: 20, calm: 21 })?.verdict).toBe("Buena");
    expect(recoveryVerdict(74)?.verdict).toBe("Mejor que de costumbre");
    expect(recoveryVerdict(50)?.verdict).toBe("Como siempre");
    expect(recoveryVerdict(30)?.tone).toBe("fair");
    expect(recoveryLine(1.2, -0.8)).toBe("VFC alta, reposo bajo");
  });

  it("los pasos con su media", () => {
    const said = moveVerdict({ today: 3200, mean_7: 8000, mean_7_past: 8100, mean_30: 9000, goal: 8000 });
    expect(said).toEqual({ verdict: "3.200 pasos", tone: "neutral", detail: "media de 7 días: 8.100" });
  });

  it("la frase junta lo que haya", () => {
    expect(
      daySentence({
        sleep: { verdict: "Buena", tone: "good" },
        recovery: { verdict: "Mejor que de costumbre", tone: "good" },
        train: { verdict: "Algo por debajo", tone: "neutral" },
      }),
    ).toBe("Dormiste bien y llegas mejor que de costumbre. Esta semana vas algo por debajo de tu ritmo.");
    expect(daySentence({})).toBe("");
  });

  it("los días de la semana, con lo hecho y lo que falta", () => {
    const days = weekDots([], new Date("2026-11-05T12:00:00"));
    expect(days.map((one) => one.state)).toEqual(["missed", "missed", "missed", "today", "future", "future", "future"]);
  });
});
