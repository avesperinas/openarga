import { renderToString } from "react-dom/server";

import type { Catalogue, Editor } from "./api";
import { SQUAT } from "./fixtures";
import { PlanScreen, defaultVariantName, normalize } from "./Plan";

const SETTINGS = { weekly_goal: 5, unit: "kg", default_increments: {} };
const EMPTY_CATALOGUE: Catalogue = { exercises: [], gyms: [], muscles: [] };
const NOTHING: Editor = { plan: null, published: null, draft: null, rotation_version: null };

const render = (editor: Editor, catalogue = EMPTY_CATALOGUE) =>
  renderToString(<PlanScreen initial={{ editor, catalogue, settings: SETTINGS }} />).replaceAll("<!-- -->", "");

describe("la pantalla del plan", () => {
  it("sin plan, se crea desde aquí, y los ajustes ya no están: tienen su pestaña", () => {
    const html = render(NOTHING);

    expect(html).toContain("Crea tu plan");
    expect(html).toContain("Crear plan");
    expect(html).not.toContain("Objetivo semanal");
  });

  it("un borrador vacío dice qué falta para publicar", () => {
    const html = render({
      ...NOTHING,
      plan: { id: "p", name: "PPL" },
      draft: { id: "v1", number: 1, valid_from: null, published_at: null, days: [] },
    });

    expect(html).toContain("borrador de la versión 1");
    expect(html).toContain("Añade al menos un día.");
    expect(html).toMatch(/disabled=""[^>]*>.*Publicar versión 1/);
    expect(html).toContain("Añadir día");
  });

  it("lo publicado se ve con sus días y ejercicios, y avisa si la rotación sigue con otra versión", () => {
    const html = render({
      plan: { id: "p", name: "PPL" },
      published: {
        id: "v2",
        number: 2,
        valid_from: "2026-09-16",
        published_at: "2026-09-16T10:00:00Z",
        days: [{ id: "d", name: "Pierna", kind: "leg", position: 1, slots: [SQUAT] }],
      },
      draft: null,
      rotation_version: 1,
    });

    expect(html).toContain("PPL · versión 2 · desde el 16 de septiembre");
    expect(html).toContain("Sentadilla Smith o Prensa");
    expect(html).toContain("3 × 6–10");
    expect(html).toContain("La rotación en curso sigue con la versión 1");
    expect(html).toContain("Editar plan");
  });

  it("buscar no distingue tildes ni mayúsculas, y la variante tiene nombre por defecto", () => {
    expect(normalize(" Sentadilla BÚLGARA")).toBe("sentadilla bulgara");
    expect(defaultVariantName("Press banca ", "barbell")).toBe("Press banca (barra)");
  });
});

describe("el borrador y los músculos", () => {
  it("avisa de los ejercicios sin músculos, sin impedir publicar", () => {
    const catalogue: Catalogue = {
      ...EMPTY_CATALOGUE,
      exercises: [
        {
          id: "e-squat",
          name: "Sentadilla",
          pattern: "knee_dominant",
          load_type: "external",
          muscles: {},
          variants: [
            { id: "v-smith", exercise_id: "e-squat", name: "Sentadilla Smith", implement: "smith", gym_id: null, min_increment: 2.5, index_weight: 3 },
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
          days: [{ id: "d", name: "Pierna", kind: "leg", position: 1, slots: [{ ...SQUAT, options: [SQUAT.options[0]!] }] }],
        },
      },
      catalogue,
    );

    expect(html).toContain("Un ejercicio no tiene los");
    expect(html).toContain("faltan músculos");
    expect(html).not.toMatch(/disabled=""[^>]*>.*Publicar versión 1/);
  });
});
