import { renderToString } from "react-dom/server";

import type { Catalogue, Editor } from "./api";
import { SQUAT } from "./fixtures";
import { english, inLocale } from "./i18n/testing";
import { PlanScreen, defaultVariantName, normalize } from "./Plan";

const SETTINGS = { weekly_goal: 5, unit: "kg", default_increments: {} };
const EMPTY_CATALOGUE: Catalogue = { exercises: [], gyms: [], muscles: [] };
const NOTHING: Editor = { plan: null, published: null, draft: null, rotation_version: null };

const render = (editor: Editor, catalogue = EMPTY_CATALOGUE) =>
  renderToString(inLocale(<PlanScreen initial={{ editor, catalogue, settings: SETTINGS }} />)).replaceAll("<!-- -->", "");

describe("the plan screen", () => {
  it("without a plan, it is created from here, and the settings are gone: they have their tab", () => {
    const html = render(NOTHING);

    expect(html).toContain("Create your plan");
    expect(html).toContain("Create plan");
    expect(html).not.toContain("Weekly goal");
  });

  it("an empty draft says what is missing to publish", () => {
    const html = render({
      ...NOTHING,
      plan: { id: "p", name: "PPL" },
      draft: { id: "v1", number: 1, valid_from: null, published_at: null, days: [] },
    });

    expect(html).toContain("draft of version 1");
    expect(html).toContain("Add at least one day.");
    expect(html).toMatch(/disabled=""[^>]*>.*Publish version 1/);
    expect(html).toContain("Add day");
  });

  it("the published plan shows with its days and exercises, and warns if the rotation carries on with another version", () => {
    const html = render({
      plan: { id: "p", name: "PPL" },
      published: {
        id: "v2",
        number: 2,
        valid_from: "2026-09-16",
        published_at: "2026-09-16T10:00:00Z",
        days: [{ id: "d", name: "Legs", kind: "leg", position: 1, slots: [SQUAT] }],
      },
      draft: null,
      rotation_version: 1,
    });

    expect(html).toContain("PPL · version 2 · since September 16");
    expect(html).toContain("Smith machine squat or Leg press");
    expect(html).toContain("3 × 6–10");
    expect(html).toContain("The current rotation carries on with version 1");
    expect(html).toContain("Edit plan");
  });

  it("search ignores accents and case, and the variant has a default name", () => {
    expect(normalize(" Cr\u00E8me BR\u00DbL\u00C9E")).toBe("creme brulee");
    expect(defaultVariantName("Bench press ", "barbell", english)).toBe("Bench press (barbell)");
  });
});

describe("the draft and the muscles", () => {
  it("warns about exercises without muscles, without blocking publishing", () => {
    const catalogue: Catalogue = {
      ...EMPTY_CATALOGUE,
      exercises: [
        {
          id: "e-squat",
          name: "Squat",
          pattern: "knee_dominant",
          load_type: "external",
          muscles: {},
          variants: [
            { id: "v-smith", exercise_id: "e-squat", name: "Smith machine squat", implement: "smith", gym_id: null, min_increment: 2.5, index_weight: 3 },
          ],
        },
      ],
    };
    const html = render(
      {
        ...NOTHING,
        plan: { id: "p", name: "PPL" },
        draft: {
          id: "v1",
          number: 1,
          valid_from: null,
          published_at: null,
          days: [{ id: "d", name: "Legs", kind: "leg", position: 1, slots: [{ ...SQUAT, options: [SQUAT.options[0]!] }] }],
        },
      },
      catalogue,
    );

    expect(html).toContain("One exercise has no muscles");
    expect(html).toContain("muscles missing");
    expect(html).not.toMatch(/disabled=""[^>]*>.*Publish version 1/);
  });
});
