import { renderToString } from "react-dom/server";

import type { Catalogue } from "./api";
import { english, inLocale, spanish } from "./i18n/testing";
import { MusclePicker, cycleMuscle, describeMuscles, fromLevels, hasPrimary, onePrimary, toLevels } from "./Muscles";

const CATALOGUE: Catalogue = {
  exercises: [],
  gyms: [],
  muscles: [
    { id: "chest", name: "Chest", region: "upper" },
    { id: "triceps", name: "Triceps", region: "upper" },
    { id: "front_delts", name: "Front delts", region: "upper" },
    { id: "quads", name: "Quads", region: "lower" },
  ],
};

describe("the muscles of an exercise", () => {
  it("primary is 1 and secondary 0.5, both ways", () => {
    const muscles = { chest: 1, triceps: 0.5 } as const;
    expect(toLevels(muscles)).toEqual({ chest: "primary", triceps: "secondary" });
    expect(fromLevels(toLevels(muscles))).toEqual(muscles);
  });

  it("without a primary it is not complete", () => {
    expect(hasPrimary({})).toBe(false);
    expect(hasPrimary({ triceps: 0.5 })).toBe(false);
    expect(hasPrimary({ chest: 1 })).toBe(true);
  });

  it("a new primary turns the previous one into a secondary, without removing it", () => {
    expect(onePrimary({ lats: "primary" }, { lats: "primary", upper_back: "primary" })).toEqual({
      lats: "secondary",
      upper_back: "primary",
    });
    expect(onePrimary({ lats: "primary" }, { lats: "primary", biceps: "secondary" })).toEqual({
      lats: "primary",
      biceps: "secondary",
    });
  });

  it("the summary puts the primary ones first, in the language of the person", () => {
    const muscles = { triceps: 0.5, chest: 1, front_delts: 0.5 };
    expect(describeMuscles(muscles, CATALOGUE, english)).toBe("Chest · Triceps, Front delts");
    expect(describeMuscles(muscles, CATALOGUE, spanish)).toBe(
      `${spanish("muscle.chest")} · ${spanish("muscle.triceps")}, ${spanish("muscle.front_delts")}`,
    );
  });

  it("they are picked by region", () => {
    const html = renderToString(
      inLocale(<MusclePicker catalogue={CATALOGUE} value={{ quads: 1 }} onChange={() => undefined} />),
    );
    expect(html).toContain("Upper body");
    expect(html).toContain("Lower body");
    expect(html).not.toContain(">Core<");
    expect(html).toContain('aria-label="Quads: primary"');
  });

  it("on the body, tapping cycles primary, secondary and nothing (T-B05)", () => {
    expect(cycleMuscle({}, "chest")).toEqual({ chest: 1 });
    expect(cycleMuscle({ chest: 1 }, "chest")).toEqual({ chest: 0.5 });
    expect(cycleMuscle({ chest: 0.5 }, "chest")).toEqual({});
    expect(cycleMuscle({ chest: 1 }, "triceps")).toEqual({ chest: 0.5, triceps: 1 });
  });

  it("paints the choice on the body, each muscle a button with its level", () => {
    const html = renderToString(
      inLocale(<MusclePicker catalogue={CATALOGUE} value={{ chest: 1 }} onChange={() => undefined} />, "es"),
    );
    const chest = `${spanish("muscle.chest")}: ${spanish("muscle_level.primary")}`;
    expect(html).toContain(`aria-label="${spanish("muscles.works")}`);
    expect(html).toMatch(new RegExp(`data-muscle="chest"[^>]*role="button"[^>]*aria-label="${chest}"`));
  });
});
