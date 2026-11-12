import { renderToString } from "react-dom/server";

import { missing, PlugSheet, plugsOf, PUSH_URL, TokenSheet } from "./Add";
import type { Provider } from "./api";

describe("una fuente que llama", () => {
  it("enseña el token y la dirección una vez, para copiarlos al atajo", () => {
    const html = renderToString(<TokenSheet token="aaa.bbb.el-secreto" onDone={() => undefined} />);

    expect(html).toContain("aaa.bbb.el-secreto");
    expect(html).toContain(PUSH_URL);
    expect(html).toContain("no se vuelve a enseñar");
  });

  it("no pide ninguna clave para conectarse", () => {
    const apple: Provider = {
      id: "apple_health",
      name: "Apple Salud",
      description: "",
      capabilities: ["push"],
      available: true,
      single: true,
      lives_in: null,
      secrets: [],
    };

    expect(missing(apple, {})).toEqual([]);
  });
});

describe("enchufar una fuente que se ofrece", () => {
  const ical: Provider = {
    id: "ical",
    name: "Calendario publicado",
    description: "",
    capabilities: ["sync"],
    available: true,
    single: false,
    lives_in: null,
    secrets: [],
    offer: { provider: "ical", title: "Otro calendario", subtitle: "", tone: 7, asks: [], many: true, name: "{url}", group: "other" },
    inlets: [
      {
        key: "planner.calendar",
        app: "Planner",
        title: "Calendario",
        settings: [
          { key: "name", kind: "text", label: "Nombre" },
          { key: "tone", kind: "tone", label: "Color" },
        ],
      },
    ],
  };

  it("contesta a cada toma lo elegido, o lo que propone la fuente", () => {

    expect(plugsOf(ical, {}, "Pruebas")).toEqual({ "planner.calendar": { name: "Pruebas", tone: 7 } });
    expect(plugsOf(ical, { "planner.calendar": { tone: 2 } }, "Pruebas")).toEqual({ "planner.calendar": { name: "Pruebas", tone: 2 } });
  });

  it("pinta lo que pregunta cada app a la que llega", () => {
    const html = renderToString(<PlugSheet provider={ical} onClose={() => undefined} onCreated={() => undefined} />);

    expect(html).toContain("En Planner");
    expect(html).toContain("Otro calendario");
  });
});
