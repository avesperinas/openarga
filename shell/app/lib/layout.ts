import { spanOf } from "@openarga/ui";

import type {
  Breakpoint,
  Cell,
  DeskItem,
  DeskPage,
  LayoutItem,
  LayoutPage,
  Placements,
  WidgetSize,
} from "./kernel";

export { SPAN, spanOf } from "@openarga/ui";

export const BREAKPOINTS: Breakpoint[] = ["mobile", "tablet", "desktop"];
export const COLUMNS: Record<Breakpoint, number> = { mobile: 4, tablet: 8, desktop: 12 };
export const GAP: Record<Breakpoint, number> = { mobile: 12, tablet: 16, desktop: 16 };

export interface Desk {
  pages: DeskPage[];
  placements: Placements;
}

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

const boxOf = (item: LayoutItem): Box => {
  const [w, h] = spanOf(item.size);
  return { x: item.x, y: item.y, w, h };
};

const overlaps = (a: Box, b: Box): boolean =>
  a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

const collides = (items: LayoutItem[], box: Box): boolean =>
  items.some((item) => overlaps(boxOf(item), box));

const strip = ({ instance_id, source, widget, size, option }: DeskItem): DeskItem => ({
  instance_id,
  source,
  widget,
  size,
  ...(option ? { option } : {}),
});

const byReading = (a: LayoutItem, b: LayoutItem) => a.y - b.y || a.x - b.x;

export function firstFit(
  items: LayoutItem[],
  size: WidgetSize,
  columns: number,
): { x: number; y: number } {
  const [w, h] = spanOf(size);
  const lastX = Math.max(0, columns - w);
  const floor = items.reduce((low, item) => Math.max(low, item.y + spanOf(item.size)[1]), 0);

  for (let y = 0; y <= floor; y++) {
    for (let x = 0; x <= lastX; x++) {
      if (!collides(items, { x, y, w, h })) return { x, y };
    }
  }
  return { x: 0, y: floor };
}

export function arrange(
  page: DeskPage,
  columns: number,
  cells?: Record<string, Cell>,
): LayoutItem[] {
  const placed: LayoutItem[] = [];
  const later: DeskItem[] = [];

  for (const item of page.items) {
    const cell = cells?.[item.instance_id];
    if (cell) {
      const [w, h] = spanOf(item.size);
      const box = { x: cell[0], y: cell[1], w, h };
      if (box.x >= 0 && box.y >= 0 && box.x + w <= columns && !collides(placed, box)) {
        placed.push({ ...strip(item), x: box.x, y: box.y });
        continue;
      }
    }
    later.push(item);
  }
  for (const item of later) {
    placed.push({ ...strip(item), ...firstFit(placed, item.size, columns) });
  }

  const at = new Map(placed.map((item) => [item.instance_id, item]));
  return page.items.map((item) => at.get(item.instance_id)!);
}

export function arrangeAll(desk: Desk, breakpoint: Breakpoint): LayoutPage[] {
  return desk.pages.map((page) => ({
    id: page.id,
    items: arrange(page, COLUMNS[breakpoint], desk.placements[breakpoint]?.[page.id]),
  }));
}

export function prune(pages: DeskPage[], placements: Placements): Placements {
  const present = new Map(
    pages.map((page) => [page.id, new Set(page.items.map((item) => item.instance_id))]),
  );
  const result: Placements = {};
  for (const breakpoint of BREAKPOINTS) {
    const byPage = placements[breakpoint];
    if (!byPage) continue;
    const kept: Record<string, Record<string, Cell>> = {};
    for (const [pageId, cells] of Object.entries(byPage)) {
      const ids = present.get(pageId);
      if (!ids) continue;
      const alive = Object.fromEntries(Object.entries(cells).filter(([id]) => ids.has(id)));
      if (Object.keys(alive).length) kept[pageId] = alive;
    }
    if (Object.keys(kept).length) result[breakpoint] = kept;
  }
  return result;
}

const withPages = (desk: Desk, pages: DeskPage[]): Desk => ({
  pages,
  placements: prune(pages, desk.placements),
});

export function move(
  desk: Desk,
  instanceId: string,
  breakpoint: Breakpoint,
  to: { page: number; x: number; y: number },
): Desk {
  const from = desk.pages.findIndex((page) =>
    page.items.some((item) => item.instance_id === instanceId),
  );
  const target = desk.pages[to.page];
  if (from < 0 || !target) return desk;

  const columns = COLUMNS[breakpoint];
  const dragged = desk.pages[from]!.items.find((item) => item.instance_id === instanceId)!;
  const [w, h] = spanOf(dragged.size);
  const dropped: LayoutItem = {
    ...strip(dragged),
    x: clampToGrid(Math.max(0, to.x), w, columns),
    y: Math.max(0, to.y),
  };
  const box = { x: dropped.x, y: dropped.y, w, h };

  const others = arrange(target, columns, desk.placements[breakpoint]?.[target.id])
    .filter((item) => item.instance_id !== instanceId)
    .sort(byReading);
  const placed: LayoutItem[] = [dropped, ...others.filter((item) => !overlaps(boxOf(item), box))];
  for (const item of others.filter((other) => overlaps(boxOf(other), box))) {
    placed.push({ ...item, ...firstFit(placed, item.size, columns) });
  }
  placed.sort(byReading);

  const pages = desk.pages.map((page, index) => {
    if (index === to.page) return { ...page, items: placed.map(strip) };
    if (index === from) {
      return { ...page, items: page.items.filter((item) => item.instance_id !== instanceId) };
    }
    return page;
  });
  const cells = Object.fromEntries(
    placed.map((item): [string, Cell] => [item.instance_id, [item.x, item.y]]),
  );

  return {
    pages,
    placements: prune(pages, {
      ...desk.placements,
      [breakpoint]: { ...desk.placements[breakpoint], [target.id]: cells },
    }),
  };
}

export function remove(desk: Desk, instanceId: string): Desk {
  return withPages(
    desk,
    desk.pages.map((page) => ({
      ...page,
      items: page.items.filter((item) => item.instance_id !== instanceId),
    })),
  );
}

export function add(desk: Desk, pageIndex: number, widget: DeskItem): Desk {
  if (!desk.pages[pageIndex]) return desk;
  return {
    ...desk,
    pages: desk.pages.map((page, index) =>
      index === pageIndex ? { ...page, items: [...page.items, strip(widget)] } : page,
    ),
  };
}

export function resize(desk: Desk, instanceId: string, size: WidgetSize): Desk {
  return {
    ...desk,
    pages: desk.pages.map((page) => ({
      ...page,
      items: page.items.map((item) => (item.instance_id === instanceId ? { ...item, size } : item)),
    })),
  };
}

export function autoArrange(desk: Desk, breakpoint: Breakpoint, pageId: string): Desk {
  const byPage = { ...desk.placements[breakpoint] };
  delete byPage[pageId];
  return { ...desk, placements: prune(desk.pages, { ...desk.placements, [breakpoint]: byPage }) };
}

export const isArrangedByHand = (desk: Desk, breakpoint: Breakpoint, pageId: string): boolean =>
  Object.keys(desk.placements[breakpoint]?.[pageId] ?? {}).length > 0;

export function createPage(desk: Desk, id: string): Desk {
  return { ...desk, pages: [...desk.pages, { id, items: [] }] };
}

export function movePage(desk: Desk, from: number, to: number): Desk {
  if (!desk.pages[from] || to < 0 || to >= desk.pages.length) return desk;
  const pages = [...desk.pages];
  pages.splice(to, 0, pages.splice(from, 1)[0]!);
  return { ...desk, pages };
}

export function removePage(desk: Desk, index: number, keep: boolean): Desk {
  const page = desk.pages[index];
  if (!page || desk.pages.length < 2) return desk;

  const rest = desk.pages.filter((_, i) => i !== index);
  if (!keep || page.items.length === 0) return withPages(desk, rest);

  const into = Math.max(0, index - 1);
  return withPages(
    desk,
    rest.map((current, i) =>
      i === into ? { ...current, items: [...current.items, ...page.items] } : current,
    ),
  );
}

export function nearestSize(sizes: WidgetSize[], w: number, h: number): WidgetSize {
  return sizes.reduce((best, size) => {
    const [bw, bh] = spanOf(best);
    const [sw, sh] = spanOf(size);
    return Math.abs(sw - w) + Math.abs(sh - h) < Math.abs(bw - w) + Math.abs(bh - h) ? size : best;
  }, sizes[0]!);
}

export function cellAt(
  rect: { left: number; top: number; width: number; height: number },
  columns: number,
  gap: number,
  point: { x: number; y: number },
): { x: number; y: number } {
  const column = (rect.width - gap * (columns - 1)) / columns;
  const step = column + gap;
  return {
    x: Math.max(0, Math.min(columns - 1, Math.floor((point.x - rect.left) / step))),
    y: Math.max(0, Math.floor((point.y - rect.top) / step)),
  };
}

export function cellNear(
  rect: { left: number; top: number; width: number },
  columns: number,
  gap: number,
  corner: { x: number; y: number },
): { x: number; y: number } {
  const column = (rect.width - gap * (columns - 1)) / columns;
  const step = column + gap;
  return {
    x: Math.max(0, Math.min(columns - 1, Math.round((corner.x - rect.left) / step))),
    y: Math.max(0, Math.round((corner.y - rect.top) / step)),
  };
}

export function clampToGrid(x: number, width: number, columns: number): number {
  return Math.max(0, Math.min(x, columns - width));
}
