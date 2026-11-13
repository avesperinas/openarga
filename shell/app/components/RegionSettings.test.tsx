import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { type PersonPreferences, countries, fromHeaders, instanceDefaults } from "../lib/regional";
import { RegionForm, nativeName, problemsOf, sampleOf } from "./RegionSettings";

const ALEX: PersonPreferences = {
  locale: "en",
  timezone: "America/New_York",
  currency: "USD",
  country: "US",
  region: "US-NY",
  area: null,
};
const SAM: PersonPreferences = {
  locale: "es",
  timezone: "Europe/Madrid",
  currency: "EUR",
  country: "ES",
  region: "ES-NA",
  area: "pamplona",
};
const INSTANT = new Date("2026-03-01T23:30:00Z");

describe("region settings", () => {
  it("show the same moment and amount in each person's language, zone and currency", () => {
    expect(sampleOf(ALEX, INSTANT).replace(/\u202f|\u00a0/g, " ")).toBe("Sunday, March 1, 2026 at 6:30 PM · $1,234.50");
    expect(sampleOf(SAM, INSTANT).replace(/\u202f|\u00a0/g, " ")).toBe("lunes, 2 de marzo de 2026, 0:30 · 1234,50 €");
  });

  it("are written in the language being chosen", () => {
    expect(renderToStaticMarkup(<RegionForm initial={ALEX} onSave={async () => undefined} />)).toContain("Language and region");
    expect(renderToStaticMarkup(<RegionForm initial={SAM} onSave={async () => undefined} />)).toContain("Idioma y regi");
  });

  it("name each language in itself", () => {
    expect(nativeName("en")).toBe("English");
    expect(nativeName("es")).toBe("Espa\u00f1ol");
  });

  it("refuse a region outside the country and an area that is not a profile id", () => {
    expect(problemsOf(SAM)).toEqual({});
    expect(problemsOf({ ...SAM, region: "DE-BY" })).toEqual({ region: true });
    expect(problemsOf({ ...SAM, area: "Old Town" })).toEqual({ area: true });
  });

  it("list countries by their name in the person's language", () => {
    const spanish = countries("es");
    expect(spanish.find((one) => one.code === "DE")?.name).toBe("Alemania");
    expect(spanish.some((one) => one.code === "ZZ" || one.code === "EU")).toBe(false);
  });
});

describe("the person's preferences on the server", () => {
  it("come from the gateway's headers over the instance defaults", () => {
    const sent = new Headers({ "x-arga-locale": "es", "x-arga-timezone": "Europe/Berlin", "x-arga-area": "munich" });
    expect(fromHeaders(sent, instanceDefaults({ OPENARGA_CURRENCY: "CHF" }))).toEqual({
      locale: "es",
      timezone: "Europe/Berlin",
      currency: "CHF",
      country: null,
      region: null,
      area: "munich",
    });
  });
});
