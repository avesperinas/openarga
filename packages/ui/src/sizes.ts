export const SPAN = {
  "1x1": [1, 1],
  "2x1": [2, 1],
  "4x1": [4, 1],
  "1x2": [1, 2],
  "2x2": [2, 2],
  "2x4": [2, 4],
  "4x2": [4, 2],
  "4x4": [4, 4],
  "4x6": [4, 6],
} as const satisfies Record<string, readonly [number, number]>;

export type WidgetSize = keyof typeof SPAN;

export const SIZES = Object.keys(SPAN) as WidgetSize[];

export const isSize = (value: string): value is WidgetSize => value in SPAN;

export const spanOf = (size: string): readonly [number, number] =>
  isSize(size) ? SPAN[size] : SPAN["2x2"];

export const areaOf = (size: string): number => {
  const [w, h] = spanOf(size);
  return w * h;
};

const KPI_STEP: Record<WidgetSize, string> = {
  "1x1": "var(--text-kpi-s)",
  "2x1": "var(--text-kpi-s)",
  "4x1": "var(--text-kpi-s)",
  "1x2": "var(--text-kpi-s)",
  "2x2": "var(--text-kpi-m)",
  "2x4": "var(--text-kpi-l)",
  "4x2": "var(--text-kpi-l)",
  "4x4": "var(--text-kpi-xl)",
  "4x6": "var(--text-kpi-xl)",
};

export const kpiStep = (size: string): string =>
  KPI_STEP[isSize(size) ? size : "2x2"];

export const isCompact = (size: string): boolean => areaOf(size) <= 2;

export const fitsUncertaintyLine = (size: string): boolean =>
  areaOf(size) > 4 && spanOf(size)[1] > 1;

export type Layout = "tiny" | "strip" | "narrow" | "square" | "tall" | "wide" | "large";

export const layoutOf = (size: string): Layout => {
  const [w, h] = spanOf(size);
  if (h === 1) return w === 1 ? "tiny" : "strip";
  if (w === 1) return "narrow";
  if (w === 2) return h >= 4 ? "tall" : "square";
  return h >= 4 ? "large" : "wide";
};

export const seriesBudget = (size: string): number => {
  const [w] = spanOf(size);
  return w <= 1 ? 7 : w === 2 ? 14 : 30;
};
