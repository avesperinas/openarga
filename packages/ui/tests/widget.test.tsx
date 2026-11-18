import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import * as React from "react";

import { Widget, WidgetDetail, WidgetRow, WidgetRows, WidgetValue } from "../src/index";

const base = { title: "Events", hue: 1, size: "2x2", shape: "number" } as const;

const render = (element: React.ReactElement): string => renderToStaticMarkup(element);

describe("the header belongs to the system", () => {
  it("renders whole even without data", () => {
    const html = render(<Widget {...base} state="loading" />);

    expect(html).toContain("Events");
    expect(html).toContain('class="widget-dot"');
  });

  it("the tone comes from the fixed palette, not the component", () => {
    expect(render(<Widget {...base} hue={5} state="ready" />)).toContain('data-hue="5"');
  });
});

describe("the four states", () => {
  it("loading brings a skeleton shaped like the content, not a spinner", () => {
    const number = render(<Widget {...base} state="loading" />);
    const list = render(<Widget {...base} shape="list" state="loading" />);

    expect(number).toContain("widget-skeleton");
    expect(number.match(/widget-skeleton-bar/g)).toHaveLength(2);
    expect(list.match(/widget-skeleton-bar/g)).toHaveLength(4);
  });

  it("empty says a sentence and does not draw a gap", () => {
    expect(render(<Widget {...base} state="empty" />)).toContain("Nothing to show yet");
  });

  it("error KEEPS the last good value, dated", () => {
    const html = render(
      <Widget {...base} state="error" updatedAt={new Date(Date.now() - 7200_000)}>
        <WidgetValue>47</WidgetValue>
      </Widget>,
    );

    expect(html).toContain("47");
    expect(html).toContain("2 h ago");
    expect(html).toContain("Could not load");
  });

  it("disconnected offers to connect, not to retry", () => {
    const html = render(<Widget {...base} state="disconnected" onConnect={() => {}} />);

    expect(html).toContain("Conectar");
    expect(html).not.toContain("Try again");
  });

  it("disconnected says which source does not answer when the module knows", () => {
    const html = render(<Widget {...base} state="disconnected" note="No connection to Anthropic" />);

    expect(html).toContain("No connection to Anthropic");
    expect(html).not.toContain("No connector");
  });
});

describe("doubt is a modifier, not a state", () => {
  const uncertainty = { summary: "may be missing: 2 events in 1 entity not merged" };

  it("marks the number with the dotted line", () => {
    const html = render(
      <Widget {...base} state="ready" uncertainty={uncertainty}>
        <WidgetValue>7</WidgetValue>
      </Widget>,
    );

    expect(html).toContain('data-uncertain="true"');
  });

  it("without doubt there is no mark", () => {
    const html = render(
      <Widget {...base} state="ready">
        <WidgetValue>7</WidgetValue>
      </Widget>,
    );

    expect(html).not.toContain("data-uncertain");
  });

  it("in 2x2 only the dotted line; the explanation needs room", () => {
    const small = render(
      <Widget {...base} state="ready" uncertainty={uncertainty}>
        <WidgetValue>7</WidgetValue>
      </Widget>,
    );
    const medium = render(
      <Widget {...base} size="4x2" shape="list" state="ready" uncertainty={uncertainty}>
        <WidgetRows>
          <WidgetRow label="Alba Market" value="7 eventos" />
        </WidgetRows>
      </Widget>,
    );

    expect(small).not.toContain(uncertainty.summary);
    expect(medium).toContain(uncertainty.summary);
  });

  it("does not render over a state without data", () => {
    for (const state of ["empty", "loading"] as const) {
      const html = render(<Widget {...base} state={state} uncertainty={uncertainty} />);
      expect(html).not.toContain(uncertainty.summary);
    }
  });
});

describe("the header", () => {
  it("has no line below, not over a list either", () => {
    expect(render(<Widget {...base} state="ready" />)).not.toContain("widget-separator");
    expect(render(<Widget {...base} shape="list" state="ready" />)).not.toContain("widget-separator");
  });

  it("carries the app icon when the shell provides it, and otherwise the dot", () => {
    const conIcono = render(<Widget {...base} state="ready" appIcon="/training/icon.svg" />);
    expect(conIcono).toContain('class="widget-icon"');
    expect(conIcono).toContain('src="/training/icon.svg"');
    expect(conIcono).not.toContain("widget-dot");
    expect(render(<Widget {...base} state="ready" />)).toContain('class="widget-dot"');
  });

  it("puts the app's tone on the card, for the inside to read", () => {
    expect(render(<Widget {...base} hue={5} state="ready" />)).toContain('data-hue="5"');
  });
});

describe("the body", () => {
  it("is the only thing the module sets", () => {
    const html = render(
      <Widget {...base} state="ready">
        <WidgetValue>1.284</WidgetValue>
        <WidgetDetail>12 hoy</WidgetDetail>
      </Widget>,
    );

    expect(html).toContain("1.284");
    expect(html).toContain("12 hoy");
    expect(html.match(/widget-header/g)).toHaveLength(1);
  });
});

describe("what the module says shows", () => {
  it("empty, with the module's reason and not the generic sentence", () => {
    const html = render(<Widget {...base} state="empty" note="nothing connected yet" />);

    expect(html).toContain("nothing connected yet");
    expect(html).not.toContain("Nothing to show yet");
  });
});

describe("the lists", () => {
  it("each row can carry its state, as a dot and a colour", () => {
    const html = render(
      <WidgetRows>
        <WidgetRow label="BBVA" value="Caducada" tone="negative" />
        <WidgetRow label="Example Bank" value="Up to date" />
      </WidgetRows>,
    );

    expect(html).toContain('data-tone="negative"');
    expect(html).toContain("widget-row-dot");
    expect(html.match(/widget-row-dot/g)).toHaveLength(1);
  });

  it("scrolls, and if the card leads somewhere, tapping a row goes there", () => {
    const linked = render(
      <WidgetRows href="/hub">
        <WidgetRow label="BBVA" value="Caducada" />
      </WidgetRows>,
    );
    const plain = render(
      <WidgetRows>
        <WidgetRow label="BBVA" value="Caducada" />
      </WidgetRows>,
    );

    expect(linked).toMatch(/<a class="widget-rows-scroll" href="\/hub"/);
    expect(plain).toContain('<div class="widget-rows-scroll"');
  });
});

describe("the 1x1", () => {
  it("keeps the title for the screen reader even when not visible", () => {
    const html = render(<Widget {...base} size="1x1" state="loading" />);

    expect(html).toContain('data-size="1x1"');
    expect(html).toContain("Events");
  });
});
