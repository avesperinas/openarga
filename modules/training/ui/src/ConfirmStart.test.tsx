import { renderToString } from "react-dom/server";

import { ConfirmStartSheet, rotationDetail } from "./ConfirmStart";

describe("confirmar antes de empezar", () => {
  it("pregunta por el día, dice dónde cae y ofrece cancelar antes que empezar", () => {
    const html = renderToString(
      <ConfirmStartSheet
        name="Pull"
        detail={rotationDetail(3, 2, 3)}
        onCancel={() => undefined}
        onStart={async () => undefined}
      />,
    );

    expect(html).toContain("¿Empezar Pull?");
    expect(html).toContain("Rotación 3, día 2 de 3.");
    expect(html).toMatch(/Cancelar.*Empezar Pull/);
  });

  it("deja empezar otro día del plan, con los hechos marcados y el que toca elegido (T-B05)", () => {
    const html = renderToString(
      <ConfirmStartSheet
        name="Pull"
        detail={rotationDetail(3, 2, 3)}
        days={[
          { id: "d1", name: "Push", done: true },
          { id: "d2", name: "Pull", done: false },
          { id: "d3", name: "Leg", done: false },
        ]}
        chosen="d2"
        onChoose={() => undefined}
        onCancel={() => undefined}
        onStart={async () => undefined}
      />,
    );

    expect(html).toContain('aria-label="Otro día"');
    expect(html).toContain("Push ✓");
    expect(html).toMatch(/aria-checked="true"[^>]*>Pull</);
  });
});
