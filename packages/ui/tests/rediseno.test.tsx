import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  HourStrip,
  Panes,
  PhotoTile,
  Sparkline,
  SplitBar,
  Tile,
  ToggleGroup,
  ToggleRow,
  TrendTile,
  VitalCard,
  hourLevel,
  plain,
  ringMark,
} from "../src/index";

describe("the main part and its support", () => {
  it("the main part comes before the support in the DOM, and the support says its name", () => {
    const html = renderToStaticMarkup(<Panes main={<p>uno</p>} aside={<p>dos</p>} asideLabel="Atajos" />);
    expect(html.indexOf("uno")).toBeLessThan(html.indexOf("dos"));
    expect(html).toContain('aria-label="Atajos"');
    expect(html).not.toContain("data-aside-first");
  });

  it("with asideFirst it marks it for the phone without changing the DOM order", () => {
    const html = renderToStaticMarkup(<Panes main={<p>uno</p>} aside={<p>dos</p>} asideLabel="El plan" asideFirst />);
    expect(html).toContain('data-aside-first="true"');
    expect(html.indexOf("uno")).toBeLessThan(html.indexOf("dos"));
  });
});

describe("the rows that show or not", () => {
  it("the row says what it does, carries its tone and, when disabled, says so", () => {
    const html = renderToStaticMarkup(<ToggleRow name="Plan" tone={2} checked={false} onChange={() => undefined} detail="De fondo" />);
    expect(html).toContain('aria-label="Mostrar Plan"');
    expect(html).toContain('data-tone="2"');
    expect(html).toContain('data-state="off"');
    expect(html).toContain("De fondo");
  });

  it("a partly chosen group carries a mixed checkbox, and closed it renders no rows", () => {
    const html = renderToStaticMarkup(
      <ToggleGroup name="Viajes" count="1 de 3" state="mixed" onChange={() => undefined} open={false} onOpen={() => undefined}>
        <li>fila</li>
      </ToggleGroup>,
    );
    expect(html).toContain('aria-checked="mixed"');
    expect(html).toContain("1 de 3");
    expect(html).not.toContain("fila");
  });

  it("partly shown, the checkbox offers to show everything", () => {
    const html = renderToStaticMarkup(
      <ToggleGroup name="Viajes" state="mixed" onChange={() => undefined} open onOpen={() => undefined}>
        <li>fila</li>
      </ToggleGroup>,
    );
    expect(html).toContain('aria-label="Mostrar todo Viajes"');
    expect(html).toContain("fila");
  });
});

describe("at a glance", () => {
  it("with an action, the card is a button with its name and verdict, and the “i” goes outside", () => {
    const html = renderToStaticMarkup(
      <VitalCard label="Sleep" icon="moon" ring={{ value: 81, target: 100, display: "81" }} verdict="Good" tone="good" info="what it is" onOpen={() => undefined} />,
    );
    expect(html).toContain('aria-label="Sleep: Good"');
    expect(html).toContain('data-tone="good"');
    expect(html.indexOf("info-button")).toBeGreaterThan(html.indexOf("</button>"));
  });

  it("the ring's mark falls at its angle", () => {
    const half = ringMark(0.5);
    expect(half.x1).toBeCloseTo(50);
    expect(half.y1).toBeGreaterThan(50);
    const quarter = ringMark(0.25);
    expect(quarter.y1).toBeCloseTo(50);
    expect(quarter.x1).toBeGreaterThan(50);
  });

  it("a figure with its line; without an action it is not a button", () => {
    const html = renderToStaticMarkup(<TrendTile label="Reposo" value="60 lpm" weeks={[60, null, 58, 57]} />);
    expect(html).toContain("60 lpm");
    expect(html).not.toContain("<button");
  });
});

describe("the small line", () => {
  it("a gap cuts the line into two stretches and is not filled", () => {
    const html = renderToStaticMarkup(<Sparkline series={[1, 2, null, 3, 4]} />);
    expect((html.match(/M /g) ?? []).length).toBe(2);
    expect(html).not.toContain("chart-area");
  });

  it("the marks are ticks in their place", () => {
    const html = renderToStaticMarkup(<Sparkline series={[1, 2, 3]} marks={[1]} />);
    expect(html).toContain("sparkline-mark");
  });
});

describe("the 24 hours", () => {
  it("five levels, and what has not arrived yet, empty", () => {
    expect([0, 3, 10, 20, 45].map(hourLevel)).toEqual([0, 1, 2, 3, 4]);
    const html = renderToStaticMarkup(<HourStrip values={Array(24).fill(10)} label="Tension" format={(v) => `${v} min`} now={12} />);
    expect((html.match(/data-future/g) ?? []).length).toBe(11);
    expect((html.match(/<tr>/g) ?? []).length).toBe(24);
  });
});

describe("variants of what already existed", () => {
  it("the split bar with its gap and the zone colours", () => {
    const html = renderToStaticMarkup(
      <SplitBar label="Kcal" palette="zones" parts={[{ label: "A", value: "1", share: 1, hue: 1 }]} rest={{ label: "Queda", value: "2", share: 2 }} />,
    );
    expect(html).toContain('data-palette="zones"');
    expect(html).toContain("data-rest");
    expect(html).toContain("Queda");
  });

  it("the disabled cards and the shared one", () => {
    expect(renderToStaticMarkup(<Tile title="X" hue={1} muted />)).toContain("data-muted");
    const photo = renderToStaticMarkup(<PhotoTile title="Y" hue={2} icon="paw" shared badge="Vencido" badgeTone="warning" />);
    expect(photo).toContain("Compartido");
    expect(photo).toContain('data-tone="warning"');
  });

  it("thousands are grouped in four-digit numbers too", () => {
    expect(plain(1560)).toBe("1,560");
  });
});
