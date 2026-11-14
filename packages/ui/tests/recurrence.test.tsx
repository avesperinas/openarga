import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
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

describe("la frase dice lo mismo que en Python", () => {
  it.each(PHRASES)("$rrule", ({ rrule, es }) => {
    expect(describeRecurrence(fromRRule(rrule))).toBe(es);
  });
});

describe("el texto RRULE", () => {
  it.each(PHRASES)("va y vuelve: $rrule", ({ rrule }) => {
    const once = toRRule(fromRRule(rrule));
    expect(toRRule(fromRRule(once))).toBe(once);
  });

  it("sale en el orden de Python", () => {
    expect(toRRule(fromRRule("BYDAY=TH,TU;FREQ=WEEKLY;INTERVAL=1"))).toBe("FREQ=WEEKLY;BYDAY=TU,TH");
    expect(toRRule(fromRRule("RRULE:FREQ=MONTHLY;BYMONTHDAY=-1,15,1"))).toBe(
      "FREQ=MONTHLY;BYMONTHDAY=1,15,-1",
    );
  });

  it("el final es hora de pared", () => {
    expect(fromRRule("FREQ=DAILY;UNTIL=20270619T185959").until).toBe("2027-06-19T18:59:59");
    expect(fromRRule("FREQ=DAILY;UNTIL=20270619").until).toBe("2027-06-19");
    expect(() => fromRRule("FREQ=DAILY;UNTIL=20270619T185959Z")).toThrow();
  });
});

describe("el día del evento", () => {
  it("su día de la semana, sin pasar por la zona del navegador", () => {
    expect(weekdayOf("2027-03-28")).toBe("SU");
    expect(weekdayOf("2027-01-04")).toBe("MO");
  });

  it("cuál es en su mes, y el último si no hay otro detrás", () => {
    expect(positionOf("2027-01-12")).toBe(2);
    expect(positionOf("2027-01-29")).toBe(-1);
    expect(positionOf("2027-02-22")).toBe(-1);
    expect(positionOf("2027-01-01")).toBe(1);
  });

  it("las opciones rápidas salen de él", () => {
    expect(quickRules("2027-01-12").map((q) => q.label)).toEqual([
      "Cada día",
      "Cada semana, el martes",
      "De lunes a viernes",
      "Cada mes, el día 12",
      "Cada mes, el segundo martes",
      "Cada año, el 12 de enero",
    ]);
  });
});

describe("RecurrencePicker", () => {
  const render = (value: ReturnType<typeof recurrenceRule> | null) =>
    renderToStaticMarkup(<RecurrencePicker date="2027-01-12" value={value} onChange={() => {}} />);

  it("sin repetir, lo dice y no enseña el detalle", () => {
    const html = render(null);
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("No se repite");
    expect(html).toContain("Solo una vez");
    expect(html).not.toContain("recurrence-detail");
  });

  it("una opción rápida sale elegida y dicha", () => {
    const html = render(recurrenceRule("weekly", { byDay: [{ weekday: "TU" }] }));
    expect(html).toMatch(/aria-checked="true"[^>]*>Cada semana, el martes</);
    expect(html).not.toContain("recurrence-detail");
  });

  it("una regla que no es rápida abre el detalle y la frase la dice entera", () => {
    const html = render(
      recurrenceRule("weekly", { interval: 2, byDay: [{ weekday: "TU" }, { weekday: "TH" }], count: 8 }),
    );
    expect(html).toContain("recurrence-detail");
    expect(html).toMatch(/aria-checked="true"[^>]*>Personalizar…</);
    expect(html).toContain("Cada 2 semanas, martes y jueves, 8 veces");
    expect(html).toContain('aria-label="Días de la semana"');
  });

  it("es un grupo con su leyenda", () => {
    expect(render(null)).toMatch(/<fieldset class="recurrence"><legend[^>]*>Repetir<\/legend>/);
  });
});
