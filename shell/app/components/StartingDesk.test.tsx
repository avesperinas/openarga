import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { StartingDesk } from "./StartingDesk";

describe("el escritorio de partida en Ajustes", () => {
  it("dice qué trae y ofrece ponerlo en este dispositivo, sin tocar nada hasta confirmar", () => {
    const html = renderToStaticMarkup(<StartingDesk reload={() => {}} />);

    expect(html).toContain("Escritorio");
    expect(html).toContain("Hoy (agenda, tareas y el uso de Claude), Salud, Dinero y");
    expect(html).toContain("Usar el de partida del móvil");
    expect(html).not.toContain("Sustituir");
  });
});
