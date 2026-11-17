import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  IconBadge,
  Widget,
  WidgetBars,
  WidgetCalendar,
  WidgetChart,
  WidgetHeatmap,
  WidgetKpi,
  WidgetKpiDelta,
  WidgetProgress,
  WidgetRing,
  WidgetShortcuts,
  WidgetStats,
  WidgetStreak,
  WidgetUpNext,
  fitsUncertaintyLine,
  isCompact,
  kpiStep,
  spanOf,
} from "../src/index";

const render = (element: React.ReactElement): string => renderToStaticMarkup(element);

describe("the size vocabulary", () => {
  it("the four new ones and the two old ones still resolve", () => {
    expect(spanOf("1x1")).toEqual([1, 1]);
    expect(spanOf("1x2")).toEqual([1, 2]);
    expect(spanOf("2x2")).toEqual([2, 2]);
    expect(spanOf("2x4")).toEqual([2, 4]);
    expect(spanOf("4x2")).toEqual([4, 2]);
    expect(spanOf("4x4")).toEqual([4, 4]);
  });

  it("an unknown size falls back to the smallest that always fits, it does not break", () => {
    expect(spanOf("9x9")).toEqual([2, 2]);
  });

  it("the figure grows with the space, which is what makes a big KPI feel big", () => {
    const steps = ["1x1", "2x2", "2x4", "4x4"].map(kpiStep);
    expect(new Set(steps).size).toBe(4);
  });

  it("small ones do not pretend to have room", () => {
    expect(isCompact("1x1")).toBe(true);
    expect(isCompact("1x2")).toBe(true);
    expect(isCompact("2x2")).toBe(false);
    expect(fitsUncertaintyLine("1x1")).toBe(false);
    expect(fitsUncertaintyLine("2x2")).toBe(false);
    expect(fitsUncertaintyLine("4x2")).toBe(true);
  });
});

describe("the figure", () => {
  it("the server renders the real number, not a zero that then counts up", () => {
    expect(render(<WidgetKpi value={1240} />)).toContain("1,240");
  });

  it("abbreviates only when the width asks for it", () => {
    expect(render(<WidgetKpi value={9870} />)).toContain("9,870");
    expect(render(<WidgetKpi value={124000} />)).toContain("124");
  });

  it("the unit goes apart from the figure", () => {
    const html = render(<WidgetKpi value={1240} unit="km" />);
    expect(html).toContain('class="kpi-unit"');
    expect(html).toContain("km");
  });

  it("a value that arrives formatted renders as is", () => {
    expect(render(<WidgetKpi value="v0.4.1" />)).toContain("v0.4.1");
  });

  it("inherits the figure step from the containing widget's size", () => {
    const html = render(
      <Widget title="Pasos" hue={1} size="4x4" shape="number" state="ready">
        <WidgetKpi value={12} />
      </Widget>,
    );
    expect(html).toContain("--kpi-step:var(--text-kpi-xl)");
  });
});

describe("the comparison against the previous period", () => {
  it("the sign is always shown, positive too", () => {
    expect(render(<WidgetKpiDelta value={112} previous={100} />)).toContain("+12%");
    expect(render(<WidgetKpiDelta value={88} previous={100} />)).toContain("-12%");
  });

  it("the arrow says the direction without relying on colour", () => {
    expect(render(<WidgetKpiDelta value={112} previous={100} />)).toContain('data-direction="1"');
    expect(render(<WidgetKpiDelta value={88} previous={100} />)).toContain('data-direction="-1"');
    expect(render(<WidgetKpiDelta value={100} previous={100} />)).toContain('data-direction="0"');
  });

  it("going up is good or bad by domain, not by component", () => {
    const pasos = render(<WidgetKpiDelta value={112} previous={100} goodWhen="up" />);
    const gasto = render(<WidgetKpiDelta value={112} previous={100} goodWhen="down" />);

    expect(pasos).toContain('data-tone="good"');
    expect(gasto).toContain('data-tone="bad"');
  });

  it("without a good direction the change is not tinted", () => {
    expect(render(<WidgetKpiDelta value={112} previous={100} goodWhen="neutral" />)).toContain(
      'data-tone="neutral"',
    );
  });

  it("from zero to five is not 500% more", () => {
    const html = render(<WidgetKpiDelta value={5} previous={0} />);

    expect(html).toContain("no previous value");
    expect(html).not.toContain("%");
  });
});

describe("the charts", () => {
  it("an empty series says so instead of drawing a blank canvas", () => {
    expect(render(<WidgetChart series={[]} />)).toContain("No series");
    expect(render(<WidgetBars series={[]} />)).toContain("No series");
  });

  it("a single point does not break the projection", () => {
    const html = render(<WidgetChart series={[7]} />);
    expect(html).toContain("chart-line");
    expect(html).not.toContain("NaN");
  });

  it("a flat series does not divide by zero when scaling", () => {
    const html = render(<WidgetChart series={[5, 5, 5, 5]} />);
    expect(html).not.toContain("NaN");
  });

  it("the stroke does not deform when the canvas stretches", () => {
    expect(render(<WidgetChart series={[1, 4, 2]} />)).toContain('vector-effect="non-scaling-stroke"');
  });

  it("labels render only if there is one per bar", () => {
    const bien = render(<WidgetBars series={[1, 2]} labels={["L", "M"]} />);
    const mal = render(<WidgetBars series={[1, 2, 3]} labels={["L", "M"]} />);

    expect(bien).toContain("chart-labels");
    expect(mal).not.toContain("chart-labels");
  });

  it("today's bar stands out from the others", () => {
    expect(render(<WidgetBars series={[1, 2, 3]} highlight={1} />)).toContain("data-highlight");
  });

  it("the bars scale with transform and not height", () => {
    expect(render(<WidgetBars series={[5, 10]} />)).toContain("--bar:");
  });

  it("in the consistency map, zero is its own step", () => {
    const html = render(<WidgetHeatmap values={[0, 1, 4]} />);

    expect(html).toContain('data-level="0"');
    expect(html).toContain('data-level="4"');
  });
});

describe("progress", () => {
  it("going past the target fills the bar but does not stretch it", () => {
    const html = render(<WidgetProgress value={140} target={100} />);

    expect(html).toContain("--filled:1");
    expect(html).toContain("data-done");
    expect(html).toContain("Goal met");
  });

  it("without a target no fraction is invented", () => {
    expect(render(<WidgetProgress value={50} target={0} />)).toContain("--filled:0");
  });

  it("the bar announces itself as a progress bar", () => {
    const html = render(<WidgetProgress value={25} target={100} />);
    expect(html).toContain('role="progressbar"');
    expect(html).toContain('aria-valuenow="25"');
  });

  it("the ring reveals the share due, without overshooting", () => {
    const medio = render(<WidgetRing value={50} target={100} />);
    const pasado = render(<WidgetRing value={300} target={100} />);

    expect(medio).toContain("stroke-dashoffset");
    expect(pasado).toContain("stroke-dashoffset:0");
  });

  it("the ring can show the percentage instead of the value", () => {
    expect(render(<WidgetRing value={25} target={100} show="percent" />)).toContain("25%");
  });
});

describe("the streak", () => {
  it("agrees singular and plural", () => {
    expect(render(<WidgetStreak current={1} />)).toContain("day");
    expect(render(<WidgetStreak current={4} />)).toContain("days");
  });

  it("the dots count as much as the number", () => {
    const html = render(<WidgetStreak current={3} days={[true, false, true]} />);
    expect(html.match(/class="streak-day"/g)).toHaveLength(3);
  });

  it("renders no more days than fit", () => {
    const html = render(<WidgetStreak current={40} days={Array(60).fill(true)} />);
    expect(html.match(/class="streak-day"/g)).toHaveLength(14);
  });
});

describe("the calendar", () => {
  it("the week starts on Monday", () => {
    const html = render(<WidgetCalendar month={new Date(2026, 8, 1)} />);
    const week = [...html.matchAll(/calendar-weekday"[^>]*>(\w)</g)].map((match) => match[1]);

    expect(week).toEqual(["M", "T", "W", "T", "F", "S", "S"]);
  });

  it("day 1 falls in its column", () => {
    const html = render(<WidgetCalendar month={new Date(2026, 8, 1)} />);
    expect(html.match(/data-empty="true"/g)).toHaveLength(1);
  });

  it("counts the month's days without a length table", () => {
    const febrero = render(<WidgetCalendar month={new Date(2024, 1, 1)} />);
    expect(febrero.match(/role="gridcell"/g)).toHaveLength(29);
  });

  it("today wins over marked", () => {
    const html = render(<WidgetCalendar month={new Date(2026, 8, 1)} marked={[4]} today={4} />);
    expect(html).toContain('data-marked="true" data-today="true"');
  });
});

describe("the next thing and the shortcuts", () => {
  it("with nothing in view it says so", () => {
    expect(render(<WidgetUpNext events={[]} />)).toContain("Nothing ahead");
  });

  it("an unreadable date does not break the row", () => {
    const html = render(<WidgetUpNext events={[{ at: "no es una fecha", title: "Algo" }]} />);
    expect(html).toContain("Algo");
    expect(html).toContain("—");
  });

  it("shortcuts are links, not buttons that run something", () => {
    const html = render(
      <WidgetShortcuts actions={[{ label: "Entrenar", href: "/fitness", icon: "bolt" }]} />,
    );

    expect(html).toContain('href="/fitness"');
    expect(html).not.toContain("<button");
  });

  it("neither the shortcuts nor the small figures go past four", () => {
    const accesos = render(
      <WidgetShortcuts
        actions={Array.from({ length: 7 }, (_, index) => ({
          label: `A${index}`,
          href: `/a${index}`,
        }))}
      />,
    );
    const stats = render(
      <WidgetStats
        items={Array.from({ length: 7 }, (_, index) => ({ label: `S${index}`, value: index }))}
      />,
    );

    expect(accesos.match(/class="shortcut"/g)).toHaveLength(4);
    expect(stats.match(/class="stat"/g)).toHaveLength(4);
  });
});

describe("the card with a symbol", () => {
  it("renders the symbol in the tone asked, and not a colour of its own", () => {
    const html = render(<WidgetKpi value="Pull" detail="rotación 7" icon="pull" hue={2} />);

    expect(html).toContain("kpi-icon");
    expect(html).toContain('data-hue="2"');
    expect(html).toContain("Pull");
  });

  it("without a symbol, the card is the usual one", () => {
    const html = render(<WidgetKpi value={1284} unit="pasos" />);

    expect(html).not.toContain("kpi-icon");
    expect(html).not.toContain("data-with-icon");
  });

  it("with a symbol, the figure steps down so they do not compete", () => {
    const html = render(<WidgetKpi value="Push" icon="push" hue={4} />);

    expect(html).toContain("data-with-icon");
  });
});

describe("where a figure rests", () => {
  it("a figure is centred in its card, with its explanation below", () => {
    const css = readFileSync(new URL("../library.css", import.meta.url), "utf8");
    const kpi = /\.kpi \{([^}]*)\}/.exec(css)?.[1] ?? "";

    expect(kpi).toContain("align-items: center");
    expect(kpi).toContain("justify-content: center");
    expect(kpi).toContain("text-align: center");
  });
});

describe("the met goal shows", () => {
  it("the ring turns done: a tick in the centre and the sentence, without the figure", () => {
    const html = render(<WidgetRing value={3} target={3} label="of 3 this week" />);

    expect(html).toContain("data-done");
    expect(html).toContain("ring-check");
    expect(html).toContain("Met · 3 of 3");
    expect(html).not.toContain("ring-figure");
    expect(html).toContain("goal met");
  });

  it("half-loaded it is still the module's figure and label", () => {
    const html = render(<WidgetRing value={2} target={3} label="of 3 this week" />);

    expect(html).not.toContain("data-done");
    expect(html).toContain("ring-figure");
    expect(html).toContain("of 3 this week");
  });

  it("where there is room it says it in full, and a 1x1 keeps only the ring", () => {
    const grande = render(
      <Widget title="Entreno" hue={4} size="4x2" shape="number" state="ready">
        <WidgetRing value={5} target={4} label="of 4 this week" />
      </Widget>,
    );
    const pequeno = render(
      <Widget title="Entreno" hue={4} size="1x1" shape="number" state="ready">
        <WidgetRing value={1} target={4} label="of 4 this week" />
      </Widget>,
    );

    expect(grande).toContain("Goal met · 5 of 4");
    expect(pequeno).not.toContain("ring-label");
  });

  it("without a target there is nothing to meet", () => {
    expect(render(<WidgetRing value={0} target={0} />)).not.toContain("data-done");
  });
});

describe("an icon's badge", () => {
  it("carries the tone and the icon inside", () => {
    const html = render(<IconBadge name="kettlebell" hue={5} />);

    expect(html).toContain('class="icon-badge" data-hue="5"');
    expect(html).toContain("<svg");
  });
});

describe("a name instead of a figure", () => {
  it("is marked to wrap lines instead of overflowing", () => {
    expect(render(<WidgetKpi value="Cuerpo entero" />)).toContain("data-text");
    expect(render(<WidgetKpi value={12} />)).not.toContain("data-text");
    expect(render(<WidgetKpi value="12" />)).not.toContain("data-text");
  });
});

describe("tres cifras", () => {
  it("in a wide card they go in a row, and in a narrow one they do not leave a single one below", () => {
    const items = [
      { label: "Bancos", value: 2 },
      { label: "Cuentas", value: 5 },
      { label: "Última sincronización", value: "hace 2 h" },
    ];
    const ancha = render(
      <Widget title="Bancos" hue={2} size="4x2" shape="number" state="ready">
        <WidgetStats items={items} />
      </Widget>,
    );
    const estrecha = render(<WidgetStats items={items} />);

    expect(ancha).toContain("data-wide");
    expect(estrecha).not.toContain("data-wide");
    expect(readFileSync(new URL("../library.css", import.meta.url), "utf8")).toMatch(
      /\.stats\[data-count="3"\] > \.stat:first-child \{ grid-column: 1 \/ -1; \}/,
    );
  });
});
