import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  Delta,
  DisclosureList,
  DisclosureRow,
  Figures,
  HeadlineFigure,
  Inline,
  ProgressRing,
  Sequence,
  SequenceRow,
  Stack,
  WeekDots,
} from "../src/index";

const render = (element: React.ReactElement) => renderToStaticMarkup(element);
const noop = () => {};

describe("the figures", () => {
  it("a change says its direction, and with a name it reads in full", () => {
    expect(render(<Delta text="+2,5 kg" direction="up" />)).toBe('<span class="delta" data-direction="up">+2,5 kg</span>');
    expect(render(<Delta text="+2,5 kg" direction="up" label="Mejor serie: +2,5 kg" />)).toContain(
      'aria-label="Mejor serie: +2,5 kg"',
    );
  });

  it("the figures in a row, with their name and what deserves attention marked", () => {
    const html = render(
      <Figures
        items={[
          { label: "minutos", value: 75 },
          { label: "records", value: 2, lit: true },
        ]}
      />,
    );
    expect(html).toContain("<dt>minutos</dt><dd>75</dd>");
    expect(html).toContain('<div data-lit=""><dt>records</dt><dd>2</dd>');
    expect(render(<Figures items={[{ label: "11+ reps", value: "80 kg", muted: true }]} />)).toContain('data-muted=""');
  });

  it("the highlighted figure carries its unit and what changed", () => {
    const html = render(
      <HeadlineFigure label="Estimated max" value={119} unit="kg" change={{ text: "+6 kg", direction: "up" }} />,
    );
    expect(html).toContain("Estimated max");
    expect(html).toContain('class="headline-figure-unit"> kg');
    expect(html).toContain('data-direction="up">+6 kg');
  });

  it("the ring counts until complete, and complete carries its ✓", () => {
    expect(render(<ProgressRing done={2} target={4} />)).toContain('stroke-dasharray="50 100"');
    expect(render(<ProgressRing done={2} target={4} />)).toContain(">2</span>");
    expect(render(<ProgressRing done={4} target={4} />)).toContain('data-complete="true"');
    expect(render(<ProgressRing done={4} target={4} />)).toContain(">✓</span>");
  });
});

describe("the rows", () => {
  it("a folded row does not show its body; open, it does, with its label", () => {
    const closed = render(
      <DisclosureList label="Ejercicios">
        <DisclosureRow title="Squat" subtitle="3 × 6–10" open={false} onToggle={noop}>
          <p>Series</p>
        </DisclosureRow>
      </DisclosureList>,
    );
    expect(closed).toContain('aria-expanded="false"');
    expect(closed).not.toContain("<p>Series</p>");

    const open = render(
      <DisclosureRow title="Squat" tag="superset" open onToggle={noop}>
        <p>Series</p>
      </DisclosureRow>,
    );
    expect(open).toContain('aria-expanded="true"');
    expect(open).toContain("<p>Series</p>");
    expect(open).toContain('class="disclosure-tag"> · superset');
  });

  it("the steps say their state, and a done one is tapped to correct it", () => {
    const html = render(
      <Sequence>
        <li>
          <SequenceRow number={1} state="done" value="8 × 60 kg" onClick={noop} label="Set 1" />
        </li>
        <li>
          <SequenceRow number={2} state="todo" value="8 × 60 kg" />
        </li>
      </Sequence>,
    );
    expect(html).toMatch(/<button type="button" class="sequence-row" data-state="done" aria-label="Set 1">/);
    expect(html).toMatch(/<div class="sequence-row" data-state="todo">/);
  });

  it("placement needs no app CSS", () => {
    expect(render(<Stack gap="section">a</Stack>)).toBe('<div class="stack" data-gap="section">a</div>');
    expect(render(<Inline label="Actividades">a</Inline>)).toContain('role="group"');
  });
});

describe("the week, large and by kind", () => {
  it("each met day carries the colour of what was done and its ✓; today, its ring", () => {
    const html = render(
      <WeekDots
        size="large"
        label="2 de 4"
        days={[
          { day: "2026-09-14", state: "met", kind: "push" },
          { day: "2026-09-15", state: "met", kind: "pull", today: true },
        ]}
      />,
    );
    expect(html).toContain('data-size="large"');
    expect(html).toMatch(/data-state="met" data-kind="pull" data-today="true"/);
    expect(html).toContain(">✓</span>");
  });
});
