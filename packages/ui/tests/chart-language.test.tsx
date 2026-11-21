import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import es from "../src/i18n/es.json";
import { FlowMap, OTHERS, countryName, Sankey, Skeleton, TrendChart, configureRegional, foldSeries } from "../src/index";

const nodes = [
  { id: "me", name: "You", kind: "income" as const, column: 0 },
  { id: "rent", name: "Rent", kind: "expense" as const, column: 1 },
];
const flowNodes = nodes.map((one) => ({ ...one, group: "g", group_name: "G", inflow: 0, outflow: 0 }));
const links = [{ source: "me", target: "rent", value: 1500 }];
const points = [
  { day: "2026-09-01", value: 80.4 },
  { day: "2026-09-02", value: 79.6 },
];
const many = ["a", "b", "c", "d", "e", "f", "g"].map((key, index) => ({ key, name: key, values: [10 - index] }));

const SPANISH = new RegExp(
  [es["chart.as_table"], es["chart.others"], es["flow.empty"], es.loading].join("|"),
);

describe("shared chart pieces follow the interface language", () => {
  afterEach(() => configureRegional({ locale: "en-GB" }));

  it("speak English in English", () => {
    configureRegional({ locale: "en-GB" });
    const html = renderToStaticMarkup(
      <>
        <Sankey label="Flow" nodes={nodes} links={links} />
        <Sankey label="Flow" nodes={[]} links={[]} />
        <FlowMap label="Flow" nodes={flowNodes} links={[]} />
        <TrendChart label="Weight" points={points} />
        <Skeleton />
      </>,
    );
    expect(html).toContain("See as a table");
    expect(html).toContain("No movements in this range");
    expect(html).toContain("Loading");
    expect(html).not.toMatch(SPANISH);
    const folded = foldSeries(many);
    expect(folded.find((one) => one.key === OTHERS)?.name).toBe("Others");
  });

  it("speak Spanish in Spanish", () => {
    configureRegional({ locale: "es-ES" });
    const html = renderToStaticMarkup(
      <>
        <Sankey label="Flow" nodes={nodes} links={links} />
        <FlowMap label="Flow" nodes={flowNodes} links={[]} />
        <TrendChart label="Weight" points={points} />
      </>,
    );
    expect(html).toContain(es["chart.as_table"]);
    expect(html).toContain(es["flow.empty"]);
    expect(foldSeries(many).find((one) => one.key === OTHERS)?.name).toBe(es["chart.others"]);
  });

  it("name countries in the interface language", () => {
    configureRegional({ locale: "en-GB" });
    expect(countryName("ES", "?")).toBe("Spain");
    configureRegional({ locale: "es-ES" });
    expect(countryName("ES", "?")).not.toBe("Spain");
  });
});
