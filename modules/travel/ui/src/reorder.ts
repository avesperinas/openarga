import type { Block, Itinerary } from "./api";

export type Slot = string | null;

export function blocksOf(itinerary: Itinerary, slot: Slot): Block[] {
  if (slot === null) return itinerary.unscheduled;
  const day = itinerary.days.find((one) => one.day === slot);
  return (day?.items ?? []).flatMap((item) => (item.block ? [item.block] : []));
}

export function slots(itinerary: Itinerary): Slot[] {
  return [...itinerary.days.map((one) => one.day), null];
}

export function moved(itinerary: Itinerary, blockId: string, slot: Slot, index: number): Itinerary {
  const all = [...itinerary.days.flatMap((d) => blocksOf(itinerary, d.day)), ...itinerary.unscheduled];
  const block = all.find((one) => one.id === blockId);
  if (!block) return itinerary;
  const target = blocksOf(itinerary, slot).filter((one) => one.id !== blockId);
  target.splice(Math.max(0, Math.min(index, target.length)), 0, { ...block, day: slot });
  const placed = (day: Slot, list: Block[]) =>
    day === slot ? target : list.filter((one) => one.id !== blockId);
  return {
    ...itinerary,
    days: itinerary.days.map((day) => {
      const list = placed(day.day, blocksOf(itinerary, day.day)).map((one) => ({
        type: "block" as const,
        stay: null,
        leg: null,
        block: one,
      }));
      const items = day.items.flatMap((item) => (item.block ? (list.length ? [list.shift()!] : []) : [item]));
      return { ...day, items: [...items, ...list] };
    }),
    unscheduled: placed(null, itinerary.unscheduled),
  };
}

export function stepped(
  itinerary: Itinerary,
  blockId: string,
  direction: -1 | 1,
): { slot: Slot; index: number } | null {
  const order = slots(itinerary);
  const at = order.findIndex((slot) => blocksOf(itinerary, slot).some((one) => one.id === blockId));
  if (at < 0) return null;
  const here = blocksOf(itinerary, order[at]!);
  const index = here.findIndex((one) => one.id === blockId);
  const next = index + direction;
  if (next >= 0 && next < here.length) return { slot: order[at]!, index: next };
  const other = at + direction;
  if (other < 0 || other >= order.length) return null;
  const slot = order[other]!;
  return { slot, index: direction === 1 ? 0 : blocksOf(itinerary, slot).length };
}
