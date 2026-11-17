import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { CATALOGS, setLocale, t } from "./lang";
import { MODES, dateRange, daysRange, euros, monthsLabel, nights, todayIso } from "./words";

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    expect([t("action.save"), MODES.train.label, nights(2), dateRange("2025-03-07", "2025-03-09")]).toEqual([
      "Save",
      "Train",
      "2 nights",
      "7–9 Mar 2025",
    ]);
    setLocale("es");
    expect([t("action.save"), MODES.train.label, nights(2), dateRange("2025-03-07", "2025-03-09")]).toEqual([
      CATALOGS.es!["action.save"],
      CATALOGS.es!["mode.train"],
      "2 noches",
      "7–9 mar 2025",
    ]);
    expect([monthsLabel([4, 5, 6]), daysRange(1, null), euros(1234)]).toEqual(["abr–jun", "1 d\u00eda", "1234 €"]);
  });

  it("today is the day in the person's zone", () => {
    const moment = new Date("2026-11-17T23:30:00Z");
    expect(todayIso(moment, "Europe/Madrid")).toBe("2026-11-18");
    expect(todayIso(moment, "America/New_York")).toBe("2026-11-17");
  });
});
