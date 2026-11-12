import type { Day, DayInput, DayKind, SlotInput } from "./api";

export const NEW_SLOT: Omit<SlotInput, "variant_ids"> = {
  target_sets: 3,
  rep_min: 8,
  rep_max: 12,
  allow_both: false,
};

export function toInput(days: Day[]): DayInput[] {
  return days.map((day) => ({
    name: day.name,
    kind: day.kind,
    slots: day.slots
      .filter((slot) => slot.options.length > 0)
      .map((slot) => ({
        target_sets: slot.target_sets,
        rep_min: slot.rep_min,
        rep_max: slot.rep_max,
        allow_both: slot.allow_both,
        variant_ids: [...slot.options].sort((a, b) => a.priority - b.priority).map((o) => o.variant_id),
      })),
  }));
}

function move<T>(items: T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (index < 0 || target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target]!, next[index]!];
  return next;
}

export const addDay = (days: DayInput[], name: string, kind: DayKind): DayInput[] => [
  ...days,
  { name: name.trim(), kind, slots: [] },
];

export const updateDay = (days: DayInput[], index: number, patch: Partial<Omit<DayInput, "slots">>) =>
  days.map((day, i) => (i === index ? { ...day, ...patch, name: (patch.name ?? day.name).trim() } : day));

export const removeDay = (days: DayInput[], index: number) => days.filter((_, i) => i !== index);

export const moveDay = (days: DayInput[], index: number, direction: -1 | 1) => move(days, index, direction);

const onDay = (days: DayInput[], dayIndex: number, change: (slots: SlotInput[]) => SlotInput[]) =>
  days.map((day, i) => (i === dayIndex ? { ...day, slots: change(day.slots) } : day));

export const addSlot = (days: DayInput[], dayIndex: number, variantId: string) =>
  onDay(days, dayIndex, (slots) => [...slots, { ...NEW_SLOT, variant_ids: [variantId] }]);

export function updateSlot(days: DayInput[], dayIndex: number, slotIndex: number, patch: Partial<SlotInput>) {
  return onDay(days, dayIndex, (slots) =>
    slots.map((slot, i) => {
      if (i !== slotIndex) return slot;
      const next = { ...slot, ...patch };
      if (patch.rep_min !== undefined && next.rep_max < next.rep_min) next.rep_max = next.rep_min;
      if (patch.rep_max !== undefined && next.rep_min > next.rep_max) next.rep_min = next.rep_max;
      if (next.variant_ids.length < 2) next.allow_both = false;
      return next;
    }),
  );
}

export const removeSlot = (days: DayInput[], dayIndex: number, slotIndex: number) =>
  onDay(days, dayIndex, (slots) => slots.filter((_, i) => i !== slotIndex));

export const moveSlot = (days: DayInput[], dayIndex: number, slotIndex: number, direction: -1 | 1) =>
  onDay(days, dayIndex, (slots) => move(slots, slotIndex, direction));

export function addOption(days: DayInput[], dayIndex: number, slotIndex: number, variantId: string) {
  const slot = days[dayIndex]?.slots[slotIndex];
  if (!slot || slot.variant_ids.includes(variantId)) return days;
  return updateSlot(days, dayIndex, slotIndex, { variant_ids: [...slot.variant_ids, variantId] });
}

export function removeOption(days: DayInput[], dayIndex: number, slotIndex: number, variantId: string) {
  const slot = days[dayIndex]?.slots[slotIndex];
  if (!slot || slot.variant_ids.length < 2) return days;
  return updateSlot(days, dayIndex, slotIndex, {
    variant_ids: slot.variant_ids.filter((id) => id !== variantId),
  });
}

export function publishProblems(days: DayInput[]): string[] {
  if (days.length === 0) return ["Añade al menos un día."];
  return days
    .filter((day) => day.slots.length === 0)
    .map((day) => `«${day.name}» no tiene ejercicios.`);
}
