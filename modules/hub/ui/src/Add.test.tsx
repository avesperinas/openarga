import { configureRegional } from "@openarga/ui";
import { renderToString } from "react-dom/server";
import { beforeAll } from "vitest";

import { missing, PlugSheet, plugsOf, PUSH_URL, TokenSheet } from "./Add";
import type { Provider } from "./api";

beforeAll(() => configureRegional({ locale: "en-GB" }));

describe("a source that calls in", () => {
  it("shows the token and the address once, to copy them into the shortcut", () => {
    const html = renderToString(<TokenSheet token="aaa.bbb.the-secret" onDone={() => undefined} />);

    expect(html).toContain("aaa.bbb.the-secret");
    expect(html).toContain(PUSH_URL);
    expect(html).toContain("it is not shown again");
  });

  it("asks for no key to connect", () => {
    const apple: Provider = {
      id: "apple_health",
      name: "Apple Health",
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

describe("plugging in a source on offer", () => {
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

  it("answers each inlet with the choice, or what the source proposes", () => {

    expect(plugsOf(ical, {}, "Pruebas")).toEqual({ "planner.calendar": { name: "Pruebas", tone: 7 } });
    expect(plugsOf(ical, { "planner.calendar": { tone: 2 } }, "Pruebas")).toEqual({ "planner.calendar": { name: "Pruebas", tone: 2 } });
  });

  it("draws what each app it reaches asks", () => {
    const html = renderToString(<PlugSheet provider={ical} onClose={() => undefined} onCreated={() => undefined} />);

    expect(html).toContain("In Planner");
    expect(html).toContain("Otro calendario");
  });
});
