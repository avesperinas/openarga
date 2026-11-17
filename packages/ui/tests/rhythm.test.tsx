import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  Columns,
  Cover,
  CoverWall,
  DayTimeline,
  DayTimelines,
  DockBar,
  FrequencyBar,
  FrequencyRow,
  FrequencyRows,
  MediaCard,
  MediaHero,
  RingFigure,
} from "../src/index";

const render = (element: React.ReactElement) => renderToStaticMarkup(element);
const noop = () => {};

describe("the ring with its figure", () => {
  it("fills its share, with the figure inside and its name and line", () => {
    const html = render(<RingFigure share={0.42} value="42 %" label="Window" detail="ends at 18:30" />);
    expect(html).toContain('stroke-dasharray="42 100"');
    expect(html).toContain('<span class="share-ring-value">42 %</span>');
    expect(html).toContain("Window");
    expect(html).toContain("ends at 18:30");
  });

  it("without data, the ring is empty; and what goes past one stays full", () => {
    expect(render(<RingFigure share={null} value="–" label="Week" />)).not.toContain("share-ring-fill");
    expect(render(<RingFigure share={1.4} value="140 %" label="Week" />)).toContain('stroke-dasharray="100 100"');
    expect(render(<RingFigure share={0.7} value="70 %" label="Week" tone="warning" size="medium" />)).toContain(
      'data-size="medium" data-tone="warning"',
    );
  });

  it("the ring takes the colour of how it goes: ahead, on pace, careful or at the limit", () => {
    for (const tone of ["positive", "info", "warning", "negative"] as const) {
      expect(render(<RingFigure share={0.5} value="50 %" label="Week" tone={tone} />)).toContain(`data-tone="${tone}"`);
    }
  });
});

describe("how often", () => {
  it("up to the mark is normal", () => {
    const html = render(<FrequencyBar since={7} every={14} label="every 2 weeks, 7 days ago" />);
    expect(html).toContain('aria-label="every 2 weeks, 7 days ago"');
    expect(html).toContain("width:50%");
    expect(html).toContain("left:100%");
    expect(html).not.toContain("data-over");
  });

  it("past the mark, it says so, and the mark stays where it was due", () => {
    const html = render(<FrequencyBar since={16} every={8} label="every 8 days, 16 ago" />);
    expect(html).toContain('data-over="true"');
    expect(html).toContain("width:100%");
    expect(html).toContain("left:50%");
  });

  it("in its row, with its name and figure, and tapping it opens it", () => {
    const html = render(
      <FrequencyRows label="What you buy">
        <FrequencyRow title="Tomato" since={15} every={8} label="every 8 days, 15 ago" value="15 / 8 d" onClick={noop} />
      </FrequencyRows>,
    );
    expect(html).toContain('aria-label="What you buy"');
    expect(html).toContain('<button type="button" class="frequency-row">');
    expect(html).toContain('class="frequency-row-value" data-over="true">15 / 8 d');
  });

  it("with no habit yet, the bar without a mark", () => {
    expect(render(<FrequencyBar since={3} every={null} label="3 days ago" />)).not.toContain("frequency-bar-mark");
  });
});

describe("the day in 24 hours", () => {
  it("puts each mark and span at its time, and now in red", () => {
    const html = render(<DayTimeline label="Today" marks={[6]} spans={[{ from: 6, to: 11 }]} now={12} name="J" state="today" />);
    expect(html).toContain('class="day-timeline-mark" style="left:25%"');
    expect(html).toContain("left:25%;width:calc(45.83333333333333% - 25%)");
    expect(html).toContain('class="day-timeline-now" style="left:50%"');
    expect(html).toContain('data-state="today"');
    expect(html).toContain(">J</span>");
  });

  it("discreet, it marks it to render in grey; unasked, it does not", () => {
    expect(render(<DayTimeline label="Today" spans={[{ from: 6, to: 11 }]} quiet />)).toContain('data-quiet="true"');
    expect(render(<DayTimeline label="Today" spans={[{ from: 6, to: 11 }]} />)).not.toContain("data-quiet");
  });

  it("a span past midnight is cut at 24", () => {
    expect(render(<DayTimeline label="Today" spans={[{ from: 22, to: 27 }]} />)).toContain("calc(100% - 91.66666666666666%)");
  });

  it("with something to do on tap it is a button, and the hours go at the foot", () => {
    const html = render(
      <DayTimelines>
        <DayTimeline label="Lunes" name="L" onClick={noop} />
      </DayTimelines>,
    );
    expect(html).toContain('<button type="button" class="day-timeline"');
    expect(html).toContain('<span class="day-timeline-hours"><span>0</span><span>6</span>');
  });
});

describe("bottom bar and covers", () => {
  it("the bottom bar carries its text and its action", () => {
    const html = render(<DockBar title="4 in the cart" detail="Bread and 3 more" action={{ label: "Finish", onClick: noop }} />);
    expect(html).toContain('aria-label="4 in the cart"');
    expect(html).toContain("Bread and 3 more");
    expect(html).toContain(">Finish</button>");
  });

  it("a cover without an image is its title; the wall opens them by id", () => {
    expect(render(<Cover title="A book" subtitle="Someone" />)).toContain('<span class="cover-title">A book</span>');
    expect(render(<Cover title="A book" src="/x.jpg" />)).toContain('alt="Cover of A book"');
    const wall = render(<CoverWall items={[{ id: "b1", title: "Uno", note: "★★★", muted: true }]} onOpen={noop} />);
    expect(wall).toContain('aria-label="Uno"');
    expect(wall).toContain('data-muted="true"');
    expect(wall).toContain("★★★");
  });
});

describe("place and highlight", () => {
  it("the columns say how many there are", () => {
    expect(render(<Columns count={3}><span>a</span></Columns>)).toBe('<div class="columns" data-count="3"><span>a</span></div>');
  });

  it("the card of what you have on opens on tap and carries its action apart", () => {
    const html = render(
      <MediaCard
        media={<Cover title="A book" />}
        title="A book"
        lines={["Alguien", "Desde el 1 oct"]}
        onOpen={noop}
        action={{ label: "Terminado hoy", icon: "done", onClick: noop }}
      />,
    );
    expect(html).toContain('<button type="button" class="media-card-open">');
    expect(html).toContain('class="media-card-line" data-first="true">Alguien');
    expect(html).toContain("Terminado hoy");
  });

  it("the large image is centred with its content below", () => {
    const html = render(<MediaHero media={<Cover title="A book" size="hero" />}><p>Someone</p></MediaHero>);
    expect(html).toContain('<section class="media-hero">');
    expect(html).toContain('<div class="media-hero-text"><p>Someone</p></div>');
  });
});

