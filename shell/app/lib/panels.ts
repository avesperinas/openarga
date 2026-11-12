import { type PanelBlock, type PanelHeadline, type PanelHue, type PanelTab, type PanelTone, spanOf } from "@openarga/ui";

import type { CatalogueEntry, DeskItem } from "./kernel";

export type AreaKey = "day" | "money" | "health" | "work" | "home" | "leisure" | "mind";

export interface PanelContribution {
  area: AreaKey;
  order?: number;
  updated_at?: string;
  headlines?: (PanelHeadline & { priority?: number })[];
  tabs?: PanelTab[];
  questions?: { text: string; words: string[]; tab: string; block?: number }[];
}

export interface Contributor {
  source: string;
  name: string;
  panel: PanelContribution;
}

export interface Answer {
  area: AreaKey;
  text: string;
  words: string[];
  tab: string;
  block: PanelBlock | null;
}

export interface Area {
  key: AreaKey;
  label: string;
  apps: string;
  hue: PanelHue;
  icon: string;
  headline: (PanelHeadline & { priority?: number }) | null;
  tabs: PanelTab[];
  answers: Answer[];
}

export const AREAS: { key: AreaKey; label: string; hue: PanelHue; icon: string }[] = [
  { key: "day", label: "Día", hue: 6, icon: "calendar" },
  { key: "money", label: "Dinero", hue: 2, icon: "wallet" },
  { key: "health", label: "Salud", hue: 5, icon: "heart" },
  { key: "work", label: "Trabajo", hue: 4, icon: "contract" },
  { key: "home", label: "Casa", hue: 1, icon: "home" },
  { key: "leisure", label: "Ocio", hue: 7, icon: "plane" },
  { key: "mind", label: "Mente", hue: 3, icon: "note" },
];

export const AREA_APPS: Record<AreaKey, string[]> = {
  day: ["planner", "goals"],
  money: ["money"],
  health: ["vitals", "training", "macros"],
  work: ["study"],
  home: ["shopping", "recipes"],
  leisure: ["travel", "outings", "library"],
  mind: ["notebook", "insights"],
};

export const DEFAULT_SHOWN: AreaKey[] = ["day", "money", "health"];

export type HomePanels = { order?: string[]; hidden?: string[]; placed?: string[] };

export function hiddenOf(preferences?: HomePanels): Set<AreaKey> {
  const known = AREAS.map((area) => area.key);
  if (preferences?.hidden) return new Set(preferences.hidden.filter((key): key is AreaKey => known.includes(key as AreaKey)));
  return new Set(known.filter((key) => !DEFAULT_SHOWN.includes(key)));
}

export function shownAreas(preferences?: HomePanels): AreaKey[] {
  const hidden = hiddenOf(preferences);
  return orderOf(preferences?.order).filter((key) => !hidden.has(key));
}

export function showPanel(preferences: HomePanels | undefined, area: AreaKey): { order: string[]; hidden: string[] } {
  const shown = shownAreas(preferences).filter((key) => key !== area);
  const order = [...shown, area, ...orderOf(preferences?.order).filter((key) => key !== area && !shown.includes(key))];
  return { order, hidden: [...hiddenOf(preferences)].filter((key) => key !== area) };
}

export function hidePanel(preferences: HomePanels | undefined, area: AreaKey): { order: string[]; hidden: string[] } {
  return { order: orderOf(preferences?.order), hidden: [...new Set([...hiddenOf(preferences), area])] };
}

export function movePanel(preferences: HomePanels | undefined, area: AreaKey, step: -1 | 1): { order: string[]; hidden: string[] } {
  const order = orderOf(preferences?.order);
  const shown = shownAreas(preferences);
  const at = shown.indexOf(area);
  const other = shown[at + step];
  const hidden = [...hiddenOf(preferences)];
  if (at < 0 || !other) return { order, hidden };
  const [a, b] = [order.indexOf(area), order.indexOf(other)];
  [order[a], order[b]] = [order[b]!, order[a]!];
  return { order, hidden };
}

export const PANEL_SOURCE = "panel";
const TAB = ".tab";

export function panelEntries(): CatalogueEntry[] {
  return AREAS.flatMap((area) => [
    {
      source: PANEL_SOURCE,
      id: area.key,
      title: area.label,
      hue: area.hue,
      kind: "list",
      shape: "list",
      sizes: ["4x6", "4x4"],
      endpoint: "",
      refresh: 0,
      link: null,
      option: null,
    },
    {
      source: PANEL_SOURCE,
      id: `${area.key}${TAB}`,
      title: `Pestaña de ${area.label}`,
      hue: area.hue,
      kind: "list",
      shape: "list",
      sizes: ["2x2", "4x2", "4x4"],
      endpoint: "",
      refresh: 0,
      link: null,
      option: { label: "Pestaña", endpoint: `/panels/choices?area=${area.key}` },
    },
  ]);
}

export function panelAreaOf(item: Pick<DeskItem, "source" | "widget">): AreaKey | null {
  if (item.source !== PANEL_SOURCE) return null;
  const key = item.widget.endsWith(TAB) ? item.widget.slice(0, -TAB.length) : item.widget;
  return AREAS.some((area) => area.key === key) ? (key as AreaKey) : null;
}

export function withPanelPages<D extends { pages: { id: string; items: DeskItem[] }[] }>(
  desk: D,
  areas: AreaKey[],
  newId: () => string,
  perPage = 1,
): D {
  if (desk.pages.some((page) => page.items.some((item) => item.source === PANEL_SOURCE))) return desk;
  const lead = chunks(areas, perPage).map((group) => ({
    id: `panel-${group[0]}`,
    items: group.map((area) => ({ instance_id: newId(), source: PANEL_SOURCE, widget: area, size: "4x6" as const })),
  }));
  return { ...desk, pages: [...lead, ...desk.pages.filter((page) => !lead.some((one) => one.id === page.id))] };
}

export const PANELS_PER_DESKTOP_PAGE = 3;

function chunks<T>(list: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let at = 0; at < list.length; at += Math.max(1, size)) out.push(list.slice(at, at + Math.max(1, size)));
  return out;
}

const untouched = (page: { id: string; items: DeskItem[] }) =>
  page.id.startsWith("panel-") &&
  page.items.length === 1 &&
  page.items[0]!.source === PANEL_SOURCE &&
  !page.items[0]!.option;

export function groupPanelPages<D extends { pages: { id: string; items: DeskItem[] }[]; placements?: Record<string, Record<string, unknown>> }>(
  desk: D,
  perPage = PANELS_PER_DESKTOP_PAGE,
): D {
  const pages: D["pages"] = [];
  let changed = false;
  for (const page of desk.pages) {
    const last = pages[pages.length - 1];
    const joinable =
      last &&
      untouched(page) &&
      last.id.startsWith("panel-") &&
      last.items.length < perPage &&
      last.items.every((item) => item.source === PANEL_SOURCE && !item.option && item.size === "4x6");
    if (joinable && (untouched(last) || last.items.length > 1)) {
      pages[pages.length - 1] = { ...last, items: [...last.items, ...page.items] };
      changed = true;
    } else {
      pages.push(page);
    }
  }
  if (!changed) return desk;
  let at = -1;
  pages.forEach((page, index) => {
    if (page.id.startsWith("panel-") && page.items.every((item) => item.source === PANEL_SOURCE)) at = index;
  });
  const group = pages[at];
  const next = pages[at + 1];
  const room = (perPage - (group?.items.length ?? perPage)) * PANEL_AREA;
  const used = (next?.items ?? []).reduce((sum, item) => sum + spanOf(item.size)[0] * spanOf(item.size)[1], 0);
  let dropped: string | null = null;
  if (group && next && room > 0 && next.items.length > 0 && !next.items.some((item) => item.source === PANEL_SOURCE) && used <= room) {
    pages[at] = { ...group, items: [...group.items, ...next.items] };
    pages.splice(at + 1, 1);
    dropped = next.id;
  }
  const placements = desk.placements && dropped
    ? Object.fromEntries(Object.entries(desk.placements).map(([bp, byPage]) => [bp, Object.fromEntries(Object.entries(byPage).filter(([id]) => id !== dropped))]))
    : desk.placements;
  return { ...desk, pages, ...(placements ? { placements } : {}) };
}

const PANEL_AREA = 24;

export function placedAreas(pages: { items: Pick<DeskItem, "source" | "widget">[] }[]): AreaKey[] {
  return [...new Set(pages.flatMap((page) => page.items.map(panelAreaOf)).filter((key): key is AreaKey => key !== null))];
}

const SEPARATOR = "/";

export function actingWidget(source: string, widget: string): string {
  return `${source}${SEPARATOR}${widget}`;
}

export function splitActing(widget: string): { source: string; widget: string } {
  const at = widget.indexOf(SEPARATOR);
  return { source: widget.slice(0, at), widget: widget.slice(at + 1) };
}

function tabsOf(contributor: Contributor): PanelTab[] {
  return (contributor.panel.tabs ?? []).map((tab) => ({
    ...tab,
    id: `${contributor.source}.${tab.id}`,
    blocks: tab.blocks.map((block) =>
      block.type === "tasks" ? { ...block, widget: actingWidget(contributor.source, block.widget) } : block,
    ),
  }));
}

export function orderOf(order: string[] = []): AreaKey[] {
  const known = AREAS.map((area) => area.key);
  const mine = order.filter((key): key is AreaKey => known.includes(key as AreaKey));
  return [...new Set([...mine, ...known])];
}

export function compose(
  contributors: Contributor[],
  preferences: { order?: string[]; hidden?: string[] } = {},
): Area[] {
  const hidden = new Set(preferences.hidden ?? []);
  return orderOf(preferences.order)
    .filter((key) => !hidden.has(key))
    .flatMap((key): Area[] => {
      const meta = AREAS.find((area) => area.key === key)!;
      const mine = contributors
        .filter((one) => one.panel.area === key)
        .sort((a, b) => (a.panel.order ?? 50) - (b.panel.order ?? 50) || a.source.localeCompare(b.source));
      if (mine.length === 0) return [];
      const headlines = mine.flatMap((one, rank) => (one.panel.headlines ?? []).map((headline) => ({ headline, rank })));
      headlines.sort((a, b) => (b.headline.priority ?? 50) - (a.headline.priority ?? 50) || a.rank - b.rank);
      const tabs = mine.flatMap(tabsOf);
      const answers = mine.flatMap((one) =>
        (one.panel.questions ?? []).map((question): Answer => {
          const tab = tabs.find((candidate) => candidate.id === `${one.source}.${question.tab}`);
          return {
            area: key,
            text: question.text,
            words: question.words,
            tab: `${one.source}.${question.tab}`,
            block: tab?.blocks[question.block ?? 0] ?? null,
          };
        }),
      );
      return [
        {
          key,
          label: meta.label,
          hue: meta.hue,
          icon: meta.icon,
          apps: mine.map((one) => one.name).join(" · "),
          headline: headlines[0]?.headline ?? null,
          tabs,
          answers,
        },
      ];
    });
}

export function plain(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

export function ask(areas: Area[], query: string, limit = 6): Answer[] {
  const wanted = plain(query);
  if (wanted.length < 2) return [];
  const terms = wanted.split(/\s+/).filter((term) => term.length > 1);
  const scored = areas.flatMap((area) =>
    area.answers.map((answer) => {
      const words = answer.words.map(plain);
      const text = plain(answer.text);
      let score = 0;
      for (const word of words) {
        if (wanted.includes(word)) score += 3;
        else if (terms.some((term) => word.startsWith(term) || term.startsWith(word))) score += 2;
      }
      if (text.includes(wanted)) score += 2;
      else score += terms.filter((term) => text.includes(term)).length;
      return { answer, score };
    }),
  );
  return scored
    .filter((one) => one.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((one) => one.answer);
}

export function toneOf(area: Area): PanelTone {
  return area.headline?.tone ?? "neutral";
}
