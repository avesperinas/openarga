import { longDay } from "@openarga/ui";

import type { Category, Item, Product, ShoppingList } from "./api";

export function fold(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLocaleLowerCase("es")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

export function startsAWord(needle: string, name: string): boolean {
  const wanted = fold(needle);
  return wanted.length > 0 && ` ${fold(name)}`.includes(` ${wanted}`);
}

export interface Suggestions {
  known: Product[];
  typed: string | null;
}

export function suggest(products: Product[], query: string, limit = 6): Suggestions {
  const typed = query.trim();
  if (!typed) return { known: [], typed: null };
  const known = products.filter((one) => startsAWord(typed, one.name)).slice(0, limit);
  const exact = products.some((one) => fold(one.name) === fold(typed));
  return { known, typed: exact ? null : typed };
}

export function itemDetail(item: Pick<Item, "quantity" | "note">): string | undefined {
  const parts = [item.quantity, item.note].filter((one): one is string => Boolean(one));
  return parts.length ? parts.join(" · ") : undefined;
}

export function habitDetail(product: Pick<Product, "every" | "since" | "times">): string {
  if (product.every) return [product.every, product.since].filter(Boolean).join(" · ");
  const times = product.times === 1 ? "1 vez" : `${product.times} veces`;
  return [times, product.since].filter(Boolean).join(" · ");
}

export const dayLabel = (iso: string): string => longDay(iso);

export function withCart(list: ShoppingList, id: string, inCart: boolean): ShoppingList {
  if (inCart) {
    const item = list.groups.flatMap((group) => group.items).find((one) => one.id === id);
    if (!item) return list;
    const groups = list.groups
      .map((group) => ({ ...group, items: group.items.filter((one) => one.id !== id) }))
      .filter((group) => group.items.length > 0);
    return {
      ...list,
      groups,
      cart: [...list.cart, { ...item, in_cart: true }],
      pending: list.pending - 1,
      in_cart: list.in_cart + 1,
    };
  }
  const item = list.cart.find((one) => one.id === id);
  if (!item || !list.groups.some((group) => group.category_id === item.category_id)) return list;
  return {
    ...list,
    groups: list.groups.map((group) =>
      group.category_id === item.category_id ? { ...group, items: [...group.items, { ...item, in_cart: false }] } : group,
    ),
    cart: list.cart.filter((one) => one.id !== id),
    pending: list.pending + 1,
    in_cart: list.in_cart - 1,
  };
}

export function without(list: ShoppingList, id: string): ShoppingList {
  const inGroups = list.groups.some((group) => group.items.some((one) => one.id === id));
  const inCart = list.cart.some((one) => one.id === id);
  return {
    ...list,
    groups: list.groups
      .map((group) => ({ ...group, items: group.items.filter((one) => one.id !== id) }))
      .filter((group) => group.items.length > 0),
    cart: list.cart.filter((one) => one.id !== id),
    pending: list.pending - (inGroups ? 1 : 0),
    in_cart: list.in_cart - (inCart ? 1 : 0),
  };
}

export function withAdded(
  list: ShoppingList,
  entry: { id: string; name: string; quantity: string | null },
  products: Product[],
  categories: Category[],
): ShoppingList {
  const everything = [...list.groups.flatMap((group) => group.items), ...list.cart];
  if (everything.some((one) => fold(one.name) === fold(entry.name))) return list;
  const known = products.find((one) => fold(one.name) === fold(entry.name));
  const categoryId = known?.category_id ?? "other";
  const item: Item = {
    id: entry.id,
    product_id: known?.id ?? entry.id,
    name: known?.name ?? entry.name,
    category_id: categoryId,
    quantity: entry.quantity ?? known?.quantity ?? null,
    note: null,
    in_cart: false,
    source: "app",
  };
  const section = categories.find((one) => one.id === categoryId);
  const groups = list.groups.some((group) => group.category_id === categoryId)
    ? list.groups.map((group) => (group.category_id === categoryId ? { ...group, items: [...group.items, item] } : group))
    : [
        ...list.groups,
        { category_id: categoryId, name: section?.name ?? "Otros", emoji: section?.emoji ?? "", items: [item] },
      ].sort(
        (a, b) =>
          (categories.find((one) => one.id === a.category_id)?.position ?? 99) -
          (categories.find((one) => one.id === b.category_id)?.position ?? 99),
      );
  return { ...list, groups, pending: list.pending + 1 };
}

export function withEdited(list: ShoppingList, id: string, quantity: string | null, note: string | null): ShoppingList {
  const edit = (one: Item) => (one.id === id ? { ...one, quantity, note } : one);
  return {
    ...list,
    groups: list.groups.map((group) => ({ ...group, items: group.items.map(edit) })),
    cart: list.cart.map(edit),
  };
}

export function withFinished(list: ShoppingList): ShoppingList {
  return { ...list, cart: [], in_cart: 0 };
}

export function withSection(list: ShoppingList, id: string, categoryId: string, categories: Category[]): ShoppingList {
  const found = list.groups.flatMap((group) => group.items).find((one) => one.id === id);
  if (!found || found.category_id === categoryId) return list;
  const rest = without(list, id);
  const moved = { ...found, category_id: categoryId };
  const section = categories.find((one) => one.id === categoryId);
  const groups = rest.groups.some((group) => group.category_id === categoryId)
    ? rest.groups.map((group) => (group.category_id === categoryId ? { ...group, items: [...group.items, moved] } : group))
    : [...rest.groups, { category_id: categoryId, name: section?.name ?? "Otros", emoji: section?.emoji ?? "", items: [moved] }].sort(
        (a, b) =>
          (categories.find((one) => one.id === a.category_id)?.position ?? 99) -
          (categories.find((one) => one.id === b.category_id)?.position ?? 99),
      );
  return { ...rest, groups, pending: list.pending };
}

export function daysSince(last: string | null, today: string): number | null {
  if (!last) return null;
  const day = (iso: string) => Date.UTC(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));
  return Math.max(0, Math.round((day(today) - day(last)) / 86_400_000));
}

export function cartLine(names: string[]): string {
  if (names.length === 0) return "";
  if (names.length <= 2) return names.join(" y ");
  const first = names.slice(0, 2).map((name, index) => (index === 0 ? name : name.toLowerCase()));
  return `${first.join(", ")} y ${names.length - 2} más`;
}

