import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { InletSettings, SourceQuestions, inletValues, proposedSourceName, sourceMissing, sourceParams, type SourceAsk } from "../src/index";

const ask = (fields: Partial<SourceAsk>): SourceAsk => ({
  key: "x",
  kind: "pick",
  label: "Algo",
  source: null,
  depends_on: null,
  optional: false,
  none_label: null,
  default: null,
  choices: [],
  defaults: [],
  carries: [],
  placeholder: "",
  help: "",
  ...fields,
});

const team = ask({ key: "team", kind: "lookup", label: "Equipo", carries: [["league", "league"], ["name", "team_name"]] });
const sessions = ask({
  key: "sessions",
  kind: "checks",
  label: "Sesiones",
  choices: [
    { value: "race", label: "Carrera" },
    { value: "practice", label: "Libres" },
  ],
  defaults: ["race"],
});
const url = ask({ key: "url", kind: "url", label: "Dirección" });

describe("las preguntas de una fuente", () => {
  it("manda cada respuesta bajo su clave, con lo que viaja con lo elegido", () => {
    const params = sourceParams([team, sessions, url], {
      team: { choice: { code: "7", name: "Equipo de prueba", league: "liga.1" } },
      url: { text: "  https://example.org/a.ics " },
    });
    expect(params).toEqual({ team: "7", league: "liga.1", team_name: "Equipo de prueba", sessions: ["race"], url: "https://example.org/a.ics" });
  });

  it("dice qué falta, con palabras", () => {
    expect(sourceMissing([team], {})).toBe("Elige: equipo.");
    expect(sourceMissing([sessions], { sessions: { values: [] } })).toBe("Elige al menos una: sesiones.");
    expect(sourceMissing([url], { url: { text: " " } })).toBe("Falta: dirección.");
    expect(sourceMissing([ask({ optional: true })], {})).toBeNull();
  });

  it("propone el nombre con la plantilla de la fuente", () => {
    const source = { name: "{region|country}", title: "Festivos", asks: [ask({ key: "country" }), ask({ key: "region" })] };
    expect(proposedSourceName(source, { country: { choice: { code: "ES", name: "España" } } })).toBe("España");
    expect(proposedSourceName({ name: "{url}", title: "Otro", asks: [url] }, { url: { text: "webcal://www.example.org/x.ics" } })).toBe("example.org");
    expect(proposedSourceName({ name: "", title: "Fórmula", asks: [] }, {})).toBe("Fórmula");
  });

  it("pinta cada pregunta por su clase, y dice la que no sabe pintar", () => {
    const html = renderToStaticMarkup(
      <SourceQuestions
        asks={[sessions, url, ask({ key: "odd", kind: "slider", label: "Raro" })]}
        answers={{}}
        onChange={() => undefined}
        search={async () => ({ results: [], failed: null })}
        onError={() => undefined}
      />,
    );
    expect(html).toContain("Carrera");
    expect(html).toContain("Dirección");
    expect(html).toContain("«Raro» se elige en una versión más nueva.");
  });
});

describe("los ajustes de una toma", () => {
  const settings = [
    { key: "name", kind: "text", label: "Nombre" },
    { key: "tone", kind: "tone", label: "Color" },
    { key: "mode", kind: "choice", label: "Cómo", choices: [{ value: "events", label: "Eventos" }], default: "events" },
  ];

  it("propone el nombre de la conexión y el tono de la fuente", () => {
    expect(inletValues(settings, {}, "Osasuna", 2)).toEqual({ name: "Osasuna", tone: 2, mode: "events" });
    expect(inletValues(settings, { tone: 5 }, "Osasuna", 2).tone).toBe(5);
  });

  it("pinta el nombre, los diez tonos y las opciones", () => {
    const html = renderToStaticMarkup(<InletSettings settings={settings} values={{ name: "Osasuna", tone: 2 }} onChange={() => undefined} title="En Planner" />);
    expect(html).toContain("En Planner");
    expect(html).toContain('value="Osasuna"');
    expect(html.match(/class="source-tone"/g)?.length).toBe(10);
    expect(html).toContain('aria-checked="true" aria-label="Verde"');
    expect(html).toContain("Eventos");
  });

  it("no pinta nada si la toma no pregunta nada", () => {
    expect(renderToStaticMarkup(<InletSettings settings={[]} values={{}} onChange={() => undefined} />)).toBe("");
  });
});
