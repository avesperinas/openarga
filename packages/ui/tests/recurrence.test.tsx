import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { configureRegional } from "../src/regional";
import { describe, expect, it } from "vitest";

import {
  RecurrencePicker,
  describeRecurrence,
  fromRRule,
  positionOf,
  quickRules,
  recurrenceRule,
  toRRule,
  weekdayOf,
} from "../src/index";

const PHRASES: { rrule: string; en: string; es: string }[] = JSON.parse(
  readFileSync(new URL("../../recurrence/phrases.json", import.meta.url), "utf8"),
);

describe("the phrase says the same as in Python", () => {
  it.each(PHRASES)("$rrule", ({ rrule, en }) => {
    expect(describeRecurrence(fromRRule(rrule))).toBe(en);
  });

  it.each(PHRASES)("in Spanish: $rrule", ({ rrule, es }) => {
    configureRegional({ locale: "es-ES" });
    try {
      expect(describeRecurrence(fromRRule(rrule))).toBe(es);
    } finally {
      configureRegional({ locale: "en-GB" });
    }
  });
});

describe("the RRULE text", () => {
  it.each(PHRASES)("round trips: $rrule", ({ rrule }) => {
    const once = toRRule(fromRRule(rrule));
    expect(toRRule(fromRRule(once))).toBe(once);
  });

  it("comes out in Python's order", () => {
    expect(toRRule(fromRRule("BYDAY=TH,TU;FREQ=WEEKLY;INTERVAL=1"))).toBe("FREQ=WEEKLY;BYDAY=TU,TH");
    expect(toRRule(fromRRule("RRULE:FREQ=MONTHLY;BYMONTHDAY=-1,15,1"))).toBe(
      "FREQ=MONTHLY;BYMONTHDAY=1,15,-1",
    );
  });

  it("the end is wall-clock time", () => {
    expect(fromRRule("FREQ=DAILY;UNTIL=20270619T185959").until).toBe("2027-06-19T18:59:59");
    expect(fromRRule("FREQ=DAILY;UNTIL=20270619").until).toBe("2027-06-19");
    expect(() => fromRRule("FREQ=DAILY;UNTIL=20270619T185959Z")).toThrow();
  });
});

describe("the event's day", () => {
  it("its weekday, without going through the browser's zone", () => {
    expect(weekdayOf("2027-03-28")).toBe("SU");
    expect(weekdayOf("2027-01-04")).toBe("MO");
  });

  it("which one it is in its month, and the last if no other follows", () => {
    expect(positionOf("2027-01-12")).toBe(2);
    expect(positionOf("2027-01-29")).toBe(-1);
    expect(positionOf("2027-02-22")).toBe(-1);
    expect(positionOf("2027-01-01")).toBe(1);
  });

  it("the quick options come from it", () => {
    expect(quickRules("2027-01-12").map((q) => q.label)).toEqual([
      "Every day",
      "Every week, on Tuesday",
      "Monday to Friday",
      "Every month, on day 12",
      "Every month, on the second Tuesday",
      "Every year, on 12 January",
    ]);
  });
});

describe("RecurrencePicker", () => {
  const render = (value: ReturnType<typeof recurrenceRule> | null) =>
    renderToStaticMarkup(<RecurrencePicker date="2027-01-12" value={value} onChange={() => {}} />);

  it("without repeating, it says so and hides the detail", () => {
    const html = render(null);
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("Does not repeat");
    expect(html).toContain("Only once");
    expect(html).not.toContain("recurrence-detail");
  });

  it("a quick option shows chosen and spelled out", () => {
    const html = render(recurrenceRule("weekly", { byDay: [{ weekday: "TU" }] }));
    expect(html).toMatch(/aria-checked="true"[^>]*>Every week, on Tuesday</);
    expect(html).not.toContain("recurrence-detail");
  });

  it("a rule that is not quick opens the detail and the phrase says it in full", () => {
    const html = render(
      recurrenceRule("weekly", { interval: 2, byDay: [{ weekday: "TU" }, { weekday: "TH" }], count: 8 }),
    );
    expect(html).toContain("recurrence-detail");
    expect(html).toMatch(/aria-checked="true"[^>]*>Customise…</);
    expect(html).toContain("Every 2 weeks, Tuesday and Thursday, 8 times");
    expect(html).toContain('aria-label="Days of the week"');
  });

  it("is a group with its legend", () => {
    expect(render(null)).toMatch(/<fieldset class="recurrence"><legend[^>]*>Repeat<\/legend>/);
  });
});
