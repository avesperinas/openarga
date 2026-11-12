import { pathOf, route } from "./App";
import { continueList, prefixLine, wrap } from "./NoteEditor";
import { countdown, grade, localIso, needed, parseNumber, ruleFromServer, ruleToServer, urgency } from "./words";

const ID = "00000000-0000-4000-8000-000000000001";

describe("las direcciones", () => {
  it("cada pantalla tiene la suya y vuelve a ella", () => {
    for (const to of [
      { tab: "home" },
      { tab: "notes" },
      { tab: "note", id: ID },
      { tab: "archive" },
      { tab: "course", id: ID },
      { tab: "course", id: ID, section: "schedule" },
      { tab: "subject", id: ID },
      { tab: "session", id: ID },
      { tab: "assessment", id: ID },
    ] as const) {
      const url = new URL(pathOf(to), "http://x");
      expect(route(url.pathname, url.search)).toEqual(to);
    }
  });

  it("lo que no es una pantalla es la portada", () => {
    expect(route("/study/clase/otra-cosa")).toEqual({ tab: "home" });
    expect(route("/study/semana", "?semana=2026-09-28")).toEqual({ tab: "home" });
    expect(route("/study/estudio/" + ID + "/nada")).toEqual({ tab: "course", id: ID });
  });

  it("el enlace de la forma común abre el evaluable", () => {
    expect(route(`/study/evaluable/${ID}`)).toEqual({ tab: "assessment", id: ID });
  });
});

describe("las notas y las cuentas atrás", () => {
  it("una nota se lee en castellano, sin decimales de relleno", () => {
    expect(grade(6.25)).toBe("6,3");
    expect(grade(7)).toBe("7");
    expect(grade(85, 100)).toBe("85");
    expect(grade(null)).toBe("—");
  });

  it("lo que necesitas se redondea hacia arriba", () => {
    expect(needed(6.13)).toBe("6,2");
    expect(needed(6.1)).toBe("6,1");
    expect(needed(59.2, 100)).toBe("60");
  });

  it("un número tecleado con coma o punto", () => {
    expect(parseNumber("6,5")).toBe(6.5);
    expect(parseNumber(" 7.25 ")).toBe(7.25);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("siete")).toBeNull();
  });

  it("la cuenta atrás y su urgencia", () => {
    expect(countdown(0)).toBe("Hoy");
    expect(countdown(1)).toBe("Mañana");
    expect(countdown(5)).toBe("En 5 días");
    expect(countdown(-1)).toBe("Venció ayer");
    expect(countdown(-3)).toBe("Venció hace 3 días");
    expect(countdown(21)).toBe("En 3 semanas");
    expect([urgency(-1), urgency(1), urgency(5), urgency(20)]).toEqual(["overdue", "soon", "week", "later"]);
  });

  it("la hora local viaja con su desfase", () => {
    expect(localIso(new Date(2026, 9, 6, 18, 0))).toMatch(/^2026-10-06T18:00:00[+-]\d{2}:\d{2}$/);
  });

  it("la regla va y vuelve entre la app y el servidor sin perder nada", () => {
    const rule = {
      freq: "weekly" as const,
      interval: 1,
      byDay: [{ weekday: "TU" as const }, { weekday: "TH" as const }],
      byMonthDay: [],
      byMonth: [],
      until: "2027-01-22",
    };
    expect(ruleToServer(rule).by_day).toEqual([{ weekday: "TU" }, { weekday: "TH" }]);
    expect(ruleFromServer(ruleToServer(rule))).toEqual(rule);
  });
});

describe("el editor", () => {
  it("Intro en una lista la sigue, con su número o su casilla", () => {
    expect(continueList("- uno", 5)).toEqual({ text: "- uno\n- ", caret: 8 });
    expect(continueList("3. tres", 7)?.text).toBe("3. tres\n4. ");
    expect(continueList("- [x] hecho", 11)?.text).toBe("- [x] hecho\n- [ ] ");
    expect(continueList("texto", 5)).toBeNull();
  });

  it("Intro en una viñeta vacía acaba la lista", () => {
    expect(continueList("- uno\n- ", 8)).toEqual({ text: "- uno\n", caret: 6 });
  });

  it("negrita envuelve lo seleccionado y los prefijos van y vienen", () => {
    expect(wrap("hola mundo", 5, 10, "**")).toEqual({ text: "hola **mundo**", start: 7, end: 12 });
    expect(prefixLine("uno\ndos", 5, "## ").text).toBe("uno\n## dos");
    expect(prefixLine("uno\n## dos", 8, "## ").text).toBe("uno\ndos");
  });
});
