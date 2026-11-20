import { afterEach, describe, expect, it } from "vitest";

import { clock, compact, longDay, money, plain, todayIso } from "../src/format";
import { configureRegional, dateLocale, intlLocale, regional, regionalFrom } from "../src/regional";

const SPAIN = { locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" };
const INSTANT = "2026-03-01T23:30:00Z";

afterEach(() => configureRegional(SPAIN));

const shown = () => ({
  day: longDay(INSTANT),
  clock: clock(INSTANT),
  today: todayIso(new Date(INSTANT)),
  money: money(1234.5).replace(/\u00a0/g, " "),
  number: plain(1234567),
});

describe("the same data in two locales and two time zones", () => {
  it("in Spanish, in Madrid, in euros", () => {
    configureRegional(SPAIN);
    expect(shown()).toEqual({
      day: "Lunes, 2 de marzo",
      clock: "00:30",
      today: "2026-03-02",
      money: "1234,50 €",
      number: "1.234.567",
    });
  });

  it("in English, in New York, in dollars", () => {
    configureRegional({ locale: "en-US", timeZone: "America/New_York", currency: "USD" });
    expect(shown()).toEqual({
      day: "Sunday, March 1",
      clock: "06:30 PM",
      today: "2026-03-01",
      money: "$1,234.50",
      number: "1,234,567",
    });
  });
});

describe("regional settings", () => {
  it("come from a person's preferences, the country refining the language", () => {
    expect(regionalFrom({ locale: "en", timezone: "Europe/London", currency: "GBP", country: "GB" })).toEqual({
      locale: "en-GB",
      timeZone: "Europe/London",
      currency: "GBP",
    });
    expect(intlLocale("es", null)).toBe("es");
  });

  it("give an app's language its regional dates", () => {
    configureRegional({ ...SPAIN, locale: "en-ES" });
    expect(dateLocale("en")).toBe("en-ES");
    expect(dateLocale("es")).toBe("es");
    configureRegional(SPAIN);
  });

  it("ignore a zone or a currency that does not exist", () => {
    configureRegional({ timeZone: "Mars/Olympus", currency: "euro" });
    expect(regional()).toEqual(SPAIN);
  });
});

describe("English in Spain", () => {
  it("writes figures with the same separators as amounts", () => {
    configureRegional({ ...SPAIN, locale: "en-ES" });
    expect(compact(1619.4)).toBe("1,619.4");
    expect(money(1619.4).replace(/\u00a0/g, " ")).toBe("€1,619.40");
  });
});
