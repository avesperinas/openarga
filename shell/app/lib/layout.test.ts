import { SIZES, spanOf } from "@openarga/ui";
import { describe, expect, it } from "vitest";

import type { DeskItem, LayoutItem, WidgetSize } from "./kernel";
import {
  BREAKPOINTS,
  COLUMNS,
  type Desk,
  add,
  arrange,
  arrangeAll,
  autoArrange,
  cellAt,
  cellNear,
  clampToGrid,
  createPage,
  firstFit,
  isArrangedByHand,
  move,
  movePage,
  nearestSize,
  remove,
  removePage,
  resize,
} from "./layout";

const widget = (id: string, size: WidgetSize = "2x2"): DeskItem => ({
  instance_id: id,
  source: "kernel",
  widget: "events",
  size,
});

const placed = (id: string, x = 0, y = 0, size: WidgetSize = "2x2"): LayoutItem => ({
  ...widget(id, size),
  x,
  y,
});

const desk = (): Desk => ({
  pages: [
    { id: "inicio", items: [widget("a"), widget("b")] },
    { id: "dos", items: [widget("c")] },
  ],
  placements: {},
});

const at = (desk: Desk, breakpoint: keyof typeof COLUMNS, page: number, id: string) =>
  arrangeAll(desk, breakpoint)[page]!.items.find((item) => item.instance_id === id)!;

function random(seed: number) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 2 ** 32;
    return state / 2 ** 32;
  };
}

const overlapping = (items: LayoutItem[]) =>
  items.some((a, i) =>
    items.slice(i + 1).some((b) => {
      const [aw, ah] = spanOf(a.size);
      const [bw, bh] = spanOf(b.size);
      return a.x < b.x + bw && a.x + aw > b.x && a.y < b.y + bh && a.y + ah > b.y;
    }),
  );

describe("the same desktop in any format", () => {
  it("the same pages come out with the same widgets, without overlaps and inside the grid", () => {
    const next = random(46);
    for (let round = 0; round < 200; round++) {
      const pages = Array.from({ length: 1 + Math.floor(next() * 4) }, (_, p) => ({
        id: `p${p}`,
        items: Array.from({ length: Math.floor(next() * 9) }, (_, i) =>
          widget(`w${p}-${i}`, SIZES[Math.floor(next() * SIZES.length)]!),
        ),
      }));
      const placements = Object.fromEntries(
        BREAKPOINTS.filter(() => next() < 0.5).map((breakpoint) => [
          breakpoint,
          Object.fromEntries(
            pages.map((page) => [
              page.id,
              Object.fromEntries(
                page.items
                  .filter(() => next() < 0.6)
                  .map((item) => [
                    item.instance_id,
                    [Math.floor(next() * 14), Math.floor(next() * 6)] as [number, number],
                  ]),
              ),
            ]),
          ),
        ]),
      );
      const desktop: Desk = { pages, placements };

      for (const breakpoint of BREAKPOINTS) {
        const arranged = arrangeAll(desktop, breakpoint);
        expect(arranged.map((page) => page.id)).toEqual(pages.map((page) => page.id));
        arranged.forEach((page, index) => {
          expect(page.items.map((item) => item.instance_id)).toEqual(
            pages[index]!.items.map((item) => item.instance_id),
          );
          expect(overlapping(page.items)).toBe(false);
          for (const item of page.items) {
            expect(item.x + spanOf(item.size)[0]).toBeLessThanOrEqual(COLUMNS[breakpoint]);
          }
        });
      }
    }
  });

  it("with nothing placed by hand, it goes in order: two per row on the phone and in one row on the computer", () => {
    const hoy = { id: "hoy", items: [widget("a"), widget("b"), widget("c", "4x2")] };

    expect(arrange(hoy, 4).map(({ x, y }) => [x, y])).toEqual([
      [0, 0],
      [2, 0],
      [0, 2],
    ]);
    expect(arrange(hoy, 12).map(({ x, y }) => [x, y])).toEqual([
      [0, 0],
      [2, 0],
      [4, 0],
    ]);
  });

  it("what was placed by hand is respected, and the rest goes around it", () => {
    const hoy = { id: "hoy", items: [widget("a"), widget("b")] };

    const arranged = arrange(hoy, 12, { b: [6, 0] });

    expect(arranged.find((i) => i.instance_id === "b")).toMatchObject({ x: 6, y: 0 });
    expect(arranged.find((i) => i.instance_id === "a")).toMatchObject({ x: 0, y: 0 });
  });

  it("a hand position that does not fit this width places itself", () => {
    const hoy = { id: "hoy", items: [widget("a", "4x2")] };

    expect(arrange(hoy, 4, { a: [8, 0] })[0]).toMatchObject({ x: 0, y: 0 });
  });
});

describe("move", () => {
  it("within the same page it leaves the card where it falls and pushes away the one it covered", () => {
    const moved = move(desk(), "b", "mobile", { page: 0, x: 0, y: 0 });

    expect(at(moved, "mobile", 0, "b")).toMatchObject({ x: 0, y: 0 });
    expect(at(moved, "mobile", 0, "a")).toMatchObject({ x: 2, y: 0 });
    expect(moved.pages[0]!.items).toHaveLength(2);
  });

  it("it stays placed by hand in that format and not in the others", () => {
    const moved = move(desk(), "a", "desktop", { page: 0, x: 8, y: 0 });

    expect(isArrangedByHand(moved, "desktop", "inicio")).toBe(true);
    expect(isArrangedByHand(moved, "mobile", "inicio")).toBe(false);
    expect(at(moved, "desktop", 0, "a")).toMatchObject({ x: 8, y: 0 });
  });

  it("the formats that place themselves follow the new order", () => {
    const moved = move(desk(), "b", "desktop", { page: 0, x: 0, y: 0 });

    expect(moved.pages[0]!.items.map((i) => i.instance_id)).toEqual(["b", "a"]);
    expect(at(moved, "mobile", 0, "b")).toMatchObject({ x: 0, y: 0 });
  });

  it("what was placed by hand in another format does not move", () => {
    const enMovil = move(desk(), "b", "mobile", { page: 0, x: 0, y: 2 });
    const enOrdenador = move(enMovil, "a", "desktop", { page: 0, x: 10, y: 0 });

    expect(at(enOrdenador, "mobile", 0, "b")).toMatchObject({ x: 0, y: 2 });
  });

  it("to another page it changes page in every format", () => {
    const moved = move(desk(), "a", "tablet", { page: 1, x: 2, y: 0 });

    expect(moved.pages[0]!.items.map((i) => i.instance_id)).toEqual(["b"]);
    for (const breakpoint of BREAKPOINTS) {
      expect(arrangeAll(moved, breakpoint)[1]!.items.map((i) => i.instance_id).sort()).toEqual([
        "a",
        "c",
      ]);
    }
  });

  it("moves nothing if the target page does not exist", () => {
    expect(move(desk(), "a", "mobile", { page: 9, x: 0, y: 0 })).toEqual(desk());
  });

  it("leaves no negative coordinates or ones outside the grid", () => {
    const moved = move(desk(), "a", "mobile", { page: 0, x: 3, y: -1 });

    expect(at(moved, "mobile", 0, "a")).toMatchObject({ x: 2, y: 0 });
  });
});

describe("auto-arrange", () => {
  it("forgets what was done by hand in that format, and only that one", () => {
    const aMano = move(move(desk(), "a", "desktop", { page: 0, x: 8, y: 0 }), "b", "mobile", {
      page: 0,
      x: 0,
      y: 4,
    });

    const solo = autoArrange(aMano, "desktop", "inicio");

    expect(isArrangedByHand(solo, "desktop", "inicio")).toBe(false);
    expect(isArrangedByHand(solo, "mobile", "inicio")).toBe(true);
  });
});

describe("remove", () => {
  it("takes it out of everywhere, including hand placements", () => {
    const aMano = move(desk(), "a", "desktop", { page: 0, x: 8, y: 0 });

    const left = remove(aMano, "a");

    expect(left.pages[0]!.items.map((i) => i.instance_id)).toEqual(["b"]);
    expect(left.placements.desktop?.inicio).not.toHaveProperty("a");
  });
});

describe("add", () => {
  const entrada = widget("nuevo");

  it("puts it at the end of the given page, and each format finds it a gap", () => {
    const aMano = move(desk(), "a", "mobile", { page: 0, x: 0, y: 2 });

    const next = add(aMano, 0, entrada);

    expect(next.pages[0]!.items.at(-1)!.instance_id).toBe("nuevo");
    expect(overlapping(arrangeAll(next, "mobile")[0]!.items)).toBe(false);
    expect(next.pages[1]!.items).toHaveLength(1);
  });

  it("adds nothing if the page does not exist", () => {
    expect(add(desk(), 9, entrada)).toEqual(desk());
  });
});

describe("resize", () => {
  it("applies in every format", () => {
    const next = resize(desk(), "a", "4x2");

    for (const breakpoint of BREAKPOINTS) {
      expect(at(next, breakpoint, 0, "a").size).toBe("4x2");
    }
  });

  it("rearranges instead of overlapping the neighbour when growing", () => {
    const aMano = move(desk(), "b", "mobile", { page: 0, x: 2, y: 0 });

    const next = resize(aMano, "a", "4x2");

    expect(overlapping(arrangeAll(next, "mobile")[0]!.items)).toBe(false);
  });
});

describe("pages", () => {
  it("are created empty and at the end", () => {
    const next = createPage(desk(), "tres");

    expect(next.pages).toHaveLength(3);
    expect(next.pages[2]).toEqual({ id: "tres", items: [] });
  });

  it("are reordered taking their widgets", () => {
    const next = movePage(desk(), 1, 0);

    expect(next.pages.map((page) => page.id)).toEqual(["dos", "inicio"]);
  });

  it("are not reordered to a position that does not exist", () => {
    expect(movePage(desk(), 0, 5)).toEqual(desk());
    expect(movePage(desk(), 0, -1)).toEqual(desk());
  });

  it("deleting one keeping the widgets puts them at the end of the previous page", () => {
    const next = removePage(desk(), 1, true);

    expect(next.pages).toHaveLength(1);
    expect(next.pages[0]!.items.map((i) => i.instance_id)).toEqual(["a", "b", "c"]);
    expect(at(next, "mobile", 0, "c")).toMatchObject({ x: 0, y: 2 });
  });

  it("deleting one without keeping them deletes them with it, and their positions too", () => {
    const aMano = move(desk(), "c", "tablet", { page: 1, x: 4, y: 0 });

    const next = removePage(aMano, 1, false);

    expect(next.pages.map((p) => p.id)).toEqual(["inicio"]);
    expect(next.placements.tablet?.dos).toBeUndefined();
  });

  it("deleting the first moves its widgets to the new first", () => {
    const next = removePage(desk(), 0, true);

    expect(next.pages.map((p) => p.id)).toEqual(["dos"]);
    expect(next.pages[0]!.items.map((i) => i.instance_id)).toEqual(["c", "a", "b"]);
  });

  it("never ends up with none", () => {
    const single: Desk = { pages: [desk().pages[0]!], placements: {} };

    expect(removePage(single, 0, false)).toEqual(single);
  });
});

describe("which cell a point falls in", () => {
  const rect = { left: 0, top: 0, width: 358, height: 358 };

  it("the first column is 0", () => {
    expect(cellAt(rect, 4, 12, { x: 10, y: 10 })).toEqual({ x: 0, y: 0 });
  });

  it("the last does not go outside the grid", () => {
    expect(cellAt(rect, 4, 12, { x: 999, y: 10 }).x).toBe(3);
  });

  it("goes down a row when the point goes down", () => {
    expect(cellAt(rect, 4, 12, { x: 10, y: 120 }).y).toBe(1);
  });
});

describe("fitting whole", () => {
  it("a 4x2 cannot start at column 2 of four", () => {
    expect(clampToGrid(2, 4, 4)).toBe(0);
  });

  it("a 2x2 can start at 2", () => {
    expect(clampToGrid(2, 2, 4)).toBe(2);
  });
});

describe("first gap", () => {
  it("is the origin when the page is empty", () => {
    expect(firstFit([], "2x2", 4)).toEqual({ x: 0, y: 0 });
  });

  it("skips what is taken and goes next to it", () => {
    expect(firstFit([placed("a")], "2x2", 4)).toEqual({ x: 2, y: 0 });
  });

  it("goes down a row when no width is left", () => {
    expect(firstFit([placed("a"), placed("b", 2)], "2x2", 4)).toEqual({ x: 0, y: 2 });
  });

  it("a 4x2 does not fit next to a 2x2 even with two free columns", () => {
    expect(firstFit([placed("a")], "4x2", 4)).toEqual({ x: 0, y: 2 });
  });

  it("fills the gap the middle one left instead of going to the end", () => {
    const hueco = [placed("a"), placed("c", 0, 2), placed("d", 2, 2)];

    expect(firstFit(hueco, "2x2", 4)).toEqual({ x: 2, y: 0 });
  });
});

describe("the size closest to the drag", () => {
  const sizes = ["2x2", "4x4"] as const;

  it("picks the declared one even when dragged to one in between", () => {
    expect(nearestSize([...sizes], 3, 3)).toBe("2x2");
    expect(nearestSize([...sizes], 4, 3)).toBe("4x4");
  });

  it("with a single declared size there is nothing to choose", () => {
    expect(nearestSize(["2x2"], 12, 12)).toBe("2x2");
  });
});

describe("the T-031 criterion walkthrough", () => {
  const inicio = (): Desk => ({
    pages: [
      {
        id: "inicio",
        items: [
          widget("por-defecto-events"),
          widget("por-defecto-entities"),
          widget("por-defecto-entities_by_volume", "4x2"),
          widget("por-defecto-sync"),
          widget("por-defecto-version"),
        ],
      },
    ],
    placements: {},
  });

  it("removing, adding back from the sheet and enlarging leaves something different and valid", () => {
    const sinSync = remove(inicio(), "por-defecto-sync");
    const puesto = add(sinSync, 0, widget("nuevo-sync"));
    const grande = resize(puesto, "nuevo-sync", "4x2");

    expect(at(puesto, "mobile", 0, "nuevo-sync")).toMatchObject({ x: 2, y: 4 });
    expect(at(grande, "mobile", 0, "nuevo-sync")).toMatchObject({ size: "4x2", x: 0, y: 6 });
    expect(grande.pages[0]!.items).toHaveLength(5);
    expect(overlapping(arrangeAll(grande, "mobile")[0]!.items)).toBe(false);
  });
});

describe("cellNear", () => {
  const rect = { left: 0, top: 0, width: 388 };

  it("falls where the card's corner is, not where the finger is", () => {
    const finger = { x: 300, y: 50 };
    const grip = { x: 300, y: 50 };
    expect(cellNear(rect, 4, 12, { x: finger.x - grip.x, y: finger.y - grip.y })).toEqual({
      x: 0,
      y: 0,
    });
  });

  it("rounds to the nearest cell instead of truncating", () => {
    expect(cellNear(rect, 4, 12, { x: 60, y: 140 })).toEqual({ x: 1, y: 1 });
    expect(cellNear(rect, 4, 12, { x: 40, y: 40 })).toEqual({ x: 0, y: 0 });
  });

  it("does not go out at the top or the sides", () => {
    expect(cellNear(rect, 4, 12, { x: -80, y: -80 })).toEqual({ x: 0, y: 0 });
    expect(cellNear(rect, 4, 12, { x: 900, y: 0 }).x).toBe(3);
  });
});

describe("what was chosen when placing a widget (ADR-0099)", () => {
  it("is not lost when added or auto-arranged", () => {
    const desk = { pages: [{ id: "p", items: [] }], placements: {} };
    const placed = add(desk, 0, { instance_id: "a", source: "money", widget: "account", size: "2x2", option: "renault" });
    expect(placed.pages[0]?.items[0]?.option).toBe("renault");
    const arranged = arrange(placed.pages[0]!, 4);
    expect(arranged[0]?.option).toBe("renault");
  });
});
