import { describe, expect, it } from "vitest";

import { WHEEL_QUIET_MS, clampPage, keyDirection, groupPages, pairStart, positionOf, trackHeight, wheelPager } from "./paging";

describe("wheelPager", () => {
  it("one wheel click turns one page", () => {
    const pager = wheelPager();
    expect(pager(100, 0, 0)).toBe(1);
  });

  it("upwards goes back", () => {
    const pager = wheelPager();
    expect(pager(-100, 0, 0)).toBe(-1);
  });

  it("a trackpad brush does not change page", () => {
    const pager = wheelPager();
    expect(pager(4, 0, 0)).toBe(0);
    expect(pager(6, 0, 16)).toBe(0);
  });

  it("a trackpad gesture with inertia turns a single page", () => {
    const pager = wheelPager();
    const steps = Array.from({ length: 60 }, (_, frame) => pager(12, 0, frame * 16));
    expect(steps.filter((step) => step !== 0)).toEqual([1]);
  });

  it("after a pause, the next gesture counts again", () => {
    const pager = wheelPager();
    expect(pager(100, 0, 0)).toBe(1);
    expect(pager(100, 0, 50)).toBe(0);
    expect(pager(100, 0, 50 + WHEEL_QUIET_MS + 1)).toBe(1);
  });

  it("in Firefox the wheel arrives in lines and also turns", () => {
    const pager = wheelPager();
    expect(pager(3, 1, 0)).toBe(1);
  });
});

describe("keyDirection", () => {
  it("only the side arrows change page", () => {
    expect(keyDirection("ArrowLeft")).toBe(-1);
    expect(keyDirection("ArrowRight")).toBe(1);
    expect(keyDirection("ArrowDown")).toBe(0);
    expect(keyDirection("a")).toBe(0);
  });
});

describe("clampPage", () => {
  it("it does not go past either end", () => {
    expect(clampPage(-1, 3)).toBe(0);
    expect(clampPage(3, 3)).toBe(2);
    expect(clampPage(1, 3)).toBe(1);
  });
});

describe("trackHeight", () => {
  const heights = [400, 1200, 200];

  it("at rest it is the height of the page being viewed, not the tallest one", () => {
    expect(trackHeight(heights, 0, 390)).toBe(400);
    expect(trackHeight(heights, 780, 390)).toBe(200);
  });

  it("mid-swipe it does not change: it neither shrinks under the finger nor grows and makes Safari re-snap", () => {
    expect(trackHeight(heights, 30, 390)).toBeNull();
    expect(trackHeight(heights, 195, 390)).toBeNull();
    expect(trackHeight(heights, 760, 390)).toBeNull();
  });

  it("when snapping, even half a pixel off, it is the remaining page's", () => {
    expect(trackHeight(heights, 389.6, 390)).toBe(1200);
    expect(trackHeight(heights, 780.4, 390)).toBe(200);
  });

  it("it does not go past the ends nor divide by zero", () => {
    expect(trackHeight(heights, 5000, 390)).toBe(200);
    expect(trackHeight(heights, -20, 390)).toBe(400);
    expect(trackHeight(heights, 100, 0)).toBe(400);
    expect(trackHeight([], 0, 390)).toBe(0);
  });
});

describe("two at a time on a wide screen", () => {
  it("one at a time, each page is its own", () => {
    expect(pairStart(3, 4, 1)).toBe(3);
  });

  it("two at a time, it goes to the first of its pair", () => {
    expect([0, 1, 2, 3].map((index) => pairStart(index, 4, 2))).toEqual([0, 0, 2, 2]);
  });

  it("with an odd number, the last goes alone", () => {
    expect([0, 1, 2, 3, 4].map((index) => pairStart(index, 5, 2))).toEqual([0, 0, 2, 2, 4]);
  });

  it("with fewer pages than fit, the first", () => {
    expect(pairStart(0, 1, 2)).toBe(0);
  });
});

describe("which page the track is on", () => {
  it("with pages of different widths, at the start of each it counts as whole", () => {
    const offsets = [0, 400, 1700, 2100];
    expect(offsets.map((left) => positionOf(offsets, left))).toEqual([0, 1, 2, 3]);
  });

  it("between two, the travelled part of the one being left", () => {
    expect(positionOf([0, 400, 1700], 1050)).toBe(1.5);
  });

  it("past the ends, the first or the last", () => {
    expect(positionOf([0, 400], -20)).toBe(0);
    expect(positionOf([0, 400], 900)).toBe(1);
  });
});

describe("the pages seen at once on a wide computer", () => {
  it("four one-panel pages together; the fifth starts another group", () => {
    const spans = groupPages([4, 4, 4, 4, 4]);
    expect(spans.map((span) => span.start)).toEqual([0, 0, 0, 0, 4]);
    expect(spans.map((span) => span.edge)).toEqual(["start", "middle", "middle", "end", "only"]);
    expect(spans[0]!.group).toBe(16);
  });

  it("a twelve-column page goes with a four-column one, and two twelves go alone", () => {
    expect(groupPages([12, 4, 12, 12]).map((span) => span.start)).toEqual([0, 0, 2, 3]);
  });
});
