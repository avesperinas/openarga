import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { InletSettings, SourceQuestions, inletValues, proposedSourceName, sourceMissing, sourceParams, type SourceAsk } from "../src/index";

const ask = (fields: Partial<SourceAsk>): SourceAsk => ({
  key: "x",
  kind: "pick",
  label: "Something",
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

const team = ask({ key: "team", kind: "lookup", label: "Team", carries: [["league", "league"], ["name", "team_name"]] });
const sessions = ask({
  key: "sessions",
  kind: "checks",
  label: "Sessions",
  choices: [
    { value: "race", label: "Carrera" },
    { value: "practice", label: "Libres" },
  ],
  defaults: ["race"],
});
const url = ask({ key: "url", kind: "url", label: "Address" });

describe("a source's questions", () => {
  it("sends each answer under its key, with what travels with the choice", () => {
    const params = sourceParams([team, sessions, url], {
      team: { choice: { code: "7", name: "Test team", league: "liga.1" } },
      url: { text: "  https://example.org/a.ics " },
    });
    expect(params).toEqual({ team: "7", league: "liga.1", team_name: "Test team", sessions: ["race"], url: "https://example.org/a.ics" });
  });

  it("says what is missing, in words", () => {
    expect(sourceMissing([team], {})).toBe("Choose: team.");
    expect(sourceMissing([sessions], { sessions: { values: [] } })).toBe("Choose at least one: sessions.");
    expect(sourceMissing([url], { url: { text: " " } })).toBe("Missing: address.");
    expect(sourceMissing([ask({ optional: true })], {})).toBeNull();
  });

  it("proposes the name with the source's template", () => {
    const source = { name: "{region|country}", title: "Festivos", asks: [ask({ key: "country" }), ask({ key: "region" })] };
    expect(proposedSourceName(source, { country: { choice: { code: "ES", name: "Spain" } } })).toBe("Spain");
    expect(proposedSourceName({ name: "{url}", title: "Otro", asks: [url] }, { url: { text: "webcal://www.example.org/x.ics" } })).toBe("example.org");
    expect(proposedSourceName({ name: "", title: "Formula", asks: [] }, {})).toBe("Formula");
  });

  it("renders each question by its kind, and says which one it cannot render", () => {
    const html = renderToStaticMarkup(
      <SourceQuestions
        asks={[sessions, url, ask({ key: "odd", kind: "slider", label: "Odd" })]}
        answers={{}}
        onChange={() => undefined}
        search={async () => ({ results: [], failed: null })}
        onError={() => undefined}
      />,
    );
    expect(html).toContain("Carrera");
    expect(html).toContain("Address");
    expect(html).toContain("&#x27;Odd&#x27; is chosen in a newer version.");
  });
});

describe("an inlet's settings", () => {
  const settings = [
    { key: "name", kind: "text", label: "Nombre" },
    { key: "tone", kind: "tone", label: "Colour" },
    { key: "mode", kind: "choice", label: "How", choices: [{ value: "events", label: "Events" }], default: "events" },
  ];

  it("proposes the connection's name and the source's tone", () => {
    expect(inletValues(settings, {}, "Osasuna", 2)).toEqual({ name: "Osasuna", tone: 2, mode: "events" });
    expect(inletValues(settings, { tone: 5 }, "Osasuna", 2).tone).toBe(5);
  });

  it("renders the name, the ten tones and the options", () => {
    const html = renderToStaticMarkup(<InletSettings settings={settings} values={{ name: "Osasuna", tone: 2 }} onChange={() => undefined} title="En Planner" />);
    expect(html).toContain("En Planner");
    expect(html).toContain('value="Osasuna"');
    expect(html.match(/class="source-tone"/g)?.length).toBe(10);
    expect(html).toContain('aria-checked="true" aria-label="Green"');
    expect(html).toContain("Events");
  });

  it("renders nothing if the inlet asks nothing", () => {
    expect(renderToStaticMarkup(<InletSettings settings={[]} values={{}} onChange={() => undefined} />)).toBe("");
  });
});
