import { renderToString } from "react-dom/server";

import { route } from "./App";
import { SettingsScreen } from "./Settings";

describe("los ajustes de Training", () => {
  it("tienen su pestaña y su dirección", () => {
    expect(route("/training/ajustes")).toEqual({ screen: "settings" });
  });

  it("llevan el objetivo, el peso y los centros, y debajo lo de todas las apps", () => {
    const html = renderToString(
      <SettingsScreen
        initial={{
          settings: { weekly_goal: 5, unit: "kg", default_increments: {} },
          gyms: [{ id: "g", name: "Gimnasio de prueba", active: true }],
        }}
      />,
    ).replaceAll("<!-- -->", "");

    expect(html).toContain("Objetivo semanal");
    expect(html).toContain("Peso de hoy");
    expect(html).toContain("El mismo peso en Salud y en Macros.");
    expect(html).toContain("Gimnasio de prueba");
    expect(html).toContain("Acerca de");
    expect(html).toContain("Ajustes de arga");
  });
});
