import { afterEach } from "vitest";

import { pathOf, route } from "./App";
import { setLocale } from "./lang";
import { continueList, prefixLine, wrap } from "./NoteEditor";
import { countdown, grade, localIso, needed, parseNumber, ruleFromServer, ruleToServer, urgency } from "./words";

const ID = "00000000-0000-4000-8000-000000000001";

describe("the routes", () => {
  it("each screen has its own and returns to it", () => {
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

  it("what is not a screen is the home", () => {
    expect(route("/study/clase/otra-cosa")).toEqual({ tab: "home" });
    expect(route("/study/semana", "?semana=2026-09-28")).toEqual({ tab: "home" });
    expect(route("/study/estudio/" + ID + "/nada")).toEqual({ tab: "course", id: ID });
  });

  it("the common-shape link opens the assessment", () => {
    expect(route(`/study/evaluable/${ID}`)).toEqual({ tab: "assessment", id: ID });
  });
});

describe("grades and countdowns", () => {
  afterEach(() => setLocale("en"));

  it("a grade reads without filler decimals, with a comma in Spanish", () => {
    expect(grade(6.25)).toBe("6.3");
    expect(grade(7)).toBe("7");
    expect(grade(85, 100)).toBe("85");
    expect(grade(null)).toBe("—");
    setLocale("es");
    expect(grade(6.25)).toBe("6,3");
  });

  it("what you need rounds up", () => {
    expect(needed(6.13)).toBe("6.2");
    expect(needed(6.1)).toBe("6.1");
    expect(needed(59.2, 100)).toBe("60");
  });

  it("a number typed with a comma or a dot", () => {
    expect(parseNumber("6,5")).toBe(6.5);
    expect(parseNumber(" 7.25 ")).toBe(7.25);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("siete")).toBeNull();
  });

  it("the countdown and its urgency", () => {
    expect(countdown(0)).toBe("Today");
    expect(countdown(1)).toBe("Tomorrow");
    expect(countdown(5)).toBe("In 5 days");
    expect(countdown(-1)).toBe("Due yesterday");
    expect(countdown(-3)).toBe("Due 3 days ago");
    expect(countdown(21)).toBe("In 3 weeks");
    expect([urgency(-1), urgency(1), urgency(5), urgency(20)]).toEqual(["overdue", "soon", "week", "later"]);
    setLocale("es");
    expect(countdown(0)).toBe("Hoy");
  });

  it("the local time travels with its offset", () => {
    expect(localIso(new Date(2026, 9, 6, 18, 0))).toMatch(/^2026-10-06T18:00:00[+-]\d{2}:\d{2}$/);
  });

  it("the rule goes and comes back between the app and the server losing nothing", () => {
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

describe("the editor", () => {
  it("Enter in a list continues it, with its number or its checkbox", () => {
    expect(continueList("- uno", 5)).toEqual({ text: "- uno\n- ", caret: 8 });
    expect(continueList("3. tres", 7)?.text).toBe("3. tres\n4. ");
    expect(continueList("- [x] hecho", 11)?.text).toBe("- [x] hecho\n- [ ] ");
    expect(continueList("texto", 5)).toBeNull();
  });

  it("Enter on an empty bullet ends the list", () => {
    expect(continueList("- uno\n- ", 8)).toEqual({ text: "- uno\n", caret: 6 });
  });

  it("bold wraps the selection and prefixes toggle", () => {
    expect(wrap("hola mundo", 5, 10, "**")).toEqual({ text: "hola **mundo**", start: 7, end: 12 });
    expect(prefixLine("uno\ndos", 5, "## ").text).toBe("uno\n## dos");
    expect(prefixLine("uno\n## dos", 8, "## ").text).toBe("uno\ndos");
  });
});
