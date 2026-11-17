import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { Widget, WidgetBars, whenLabel } from "../src/index";

const NOW = new Date(2026, 8, 28, 10, 0);
const at = (days: number, hour = 9, minute = 30) =>
  new Date(2026, 8, 28 + days, hour, minute);

describe("when the next one is", () => {
  it("says the day and not just the time", () => {
    expect(whenLabel(at(0), NOW)).toBe("09:30");
    expect(whenLabel(at(1), NOW)).toBe("Tomorrow, 09:30");
    expect(whenLabel(at(3), NOW)).toBe("Thursday, 09:30");
    expect(whenLabel(at(-1), NOW)).toBe("Yesterday, 09:30");
    expect(whenLabel(at(9), NOW)).toMatch(/^7 Oct/);
  });

  it("an all-day item has no time, and another year shows the year", () => {
    expect(whenLabel(at(1, 0, 0), NOW)).toBe("Tomorrow");
    expect(whenLabel(new Date(2027, 1, 3, 0, 0), NOW)).toMatch(/2027/);
  });
});

describe("the labels of some bars", () => {
  const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep"];
  const series = months.map((_, index) => index + 1);

  it("in a narrow card they keep the first, the last and the highlighted one", () => {
    const html = renderToStaticMarkup(
      <Widget title="Pages" hue={5} size="2x2" shape="number" state="ready">
        <WidgetBars series={series} labels={months} highlight={4} />
      </Widget>,
    );
    expect(html).toContain(">ene<");
    expect(html).toContain(">may<");
    expect(html).toContain(">sep<");
    expect(html).not.toContain(">feb<");
  });

  it("outside a card all of them go: an app's screen has the width it has", () => {
    const html = renderToStaticMarkup(<WidgetBars series={series} labels={months} />);
    for (const month of months) expect(html).toContain(`>${month}<`);
  });
});
