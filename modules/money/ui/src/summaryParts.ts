import type { Kpi, Spending, Worth } from "./api";
import { isoDay, moneyWhole, percentText, say } from "./format";

export function lastYear(today = new Date()): { from: string; to: string } {
  return { from: isoDay(new Date(today.getFullYear(), today.getMonth() - 11, 1)), to: isoDay(today) };
}

export function thisMonthSpan(today = new Date()): { from: string; to: string } {
  return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), to: isoDay(today) };
}

export function change(
  value: number | null,
  previous: number | null,
  goodUp: boolean,
  against = say("change.in_12_months"),
): { text: string; tone: "positive" | "negative" | "neutral" } | undefined {
  if (value === null || previous === null || previous === 0) return undefined;
  const diff = value - previous;
  if (diff === 0) return { text: say("change.same_year"), tone: "neutral" };
  const share = diff / Math.abs(previous);
  const good = goodUp ? diff > 0 : diff < 0;
  return {
    text: `${moneyWhole(diff, true)} · ${share > 0 ? "+" : "−"}${percentText(Math.abs(share))} ${against}`,
    tone: good ? "positive" : "negative",
  };
}

export function basicByMonth(spending: Spending): { labels: string[]; basic: number[]; rest: number[] } {
  const basicKeys = new Set(spending.rows.filter((row) => row.basic).map((row) => row.key));
  const { labels, series } = spending.series;
  const basic = labels.map(() => 0);
  const rest = labels.map(() => 0);
  for (const one of series) {
    one.values.forEach((value, index) => {
      if (basicKeys.has(one.key)) basic[index]! += value;
      else rest[index]! += value;
    });
  }
  return { labels, basic, rest };
}

export function cushion(emergency: Kpi | undefined, months: number): { covered: number; share: number } | null {
  if (!emergency || emergency.value === null || !emergency.target || months <= 0) return null;
  const monthly = emergency.target / months;
  return { covered: emergency.value / monthly, share: emergency.value / emergency.target };
}

export function lastByGroup(worth: Worth): { group: string; value: number }[] {
  const last = worth.points[worth.points.length - 1];
  if (!last) return [];
  return worth.groups
    .map((group) => ({ group, value: last.by_group[group] ?? 0 }))
    .filter((one) => one.value > 0)
    .sort((a, b) => b.value - a.value);
}

const GROUP_HUES: Record<string, 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8> = {
  Cash: 1,
  Funds: 5,
  Stocks: 7,
  Pension: 6,
  Crypto: 3,
  Property: 4,
  Deposits: 2,
};

export const groupHue = (group: string): 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 => GROUP_HUES[group] ?? 8;
