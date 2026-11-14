import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { configureRegional } from "@openarga/ui";

import { english, spanish } from "./i18n/testing";
import { keptLine } from "./Shared";

beforeAll(() => configureRegional({ locale: "en-GB", timeZone: "Europe/Madrid", currency: "EUR" }));
afterAll(() => configureRegional({ locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" }));

describe("the shared money seen from the other side", () => {
  it("says who keeps it and how recent their figures are", () => {
    const now = new Date();
    now.setHours(9, 5, 0, 0);
    expect(keptLine(english, { other: "Sam", kept_at: now.toISOString() })).toBe(
      "Sam keeps it in their Money · up to date at 09:05. What you record goes into the balance within half a minute.",
    );
  });

  it("without figures yet, only who", () => {
    expect(keptLine(english, { other: "Sam", kept_at: null })).toBe("Sam keeps it in their Money.");
    expect(keptLine(spanish, { other: "Sam", kept_at: null })).toBe(spanish("shared.kept", { other: "Sam" }));
  });
});
