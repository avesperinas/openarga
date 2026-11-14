import { configureRegional } from "@openarga/ui";

import type { Item, Product, ShoppingList } from "./api";
import { english, spanish } from "./i18n/testing";
import {
  cartLine,
  daysSince,
  dayLabel,
  fold,
  habitDetail,
  itemDetail,
  sectionName,
  startsAWord,
  suggest,
  withAdded,
  withCart,
  withEdited,
  withFinished,
  withSection,
  without,
} from "./words";

function product(name: string, extra: Partial<Product> = {}): Product {
  return {
    id: name,
    name,
    category_id: "other",
    quantity: null,
    times: 0,
    last: null,
    every_days: null,
    every: null,
    since: null,
    due: false,
    on_list: false,
    ...extra,
  };
}

test("compares like the server: without accents, case or extra spaces", () => {
  expect(fold("  CR\u00c8ME   fra\u00eeche ")).toBe("creme fraiche");
  expect(fold("Pi\u00f1a")).toBe("pina");
});

test("what is typed is the start of some word", () => {
  expect(startsAWord("pot", "Potatoes")).toBe(true);
  expect(startsAWord("pot", "Sweet potatoes")).toBe(true);
  expect(startsAWord("pot", "Hotpot")).toBe(false);
  expect(startsAWord("  ", "Potatoes")).toBe(false);
});

test("typing offers what you already buy and, if none is it, adding it as it is", () => {
  const known = [product("Potatoes", { times: 5 }), product("Sweet potatoes", { times: 1 })];

  expect(suggest(known, "pot").known.map((one) => one.name)).toEqual(["Potatoes", "Sweet potatoes"]);
  expect(suggest(known, "pot").typed).toBe("pot");
  expect(suggest(known, "potatoes").typed).toBeNull();
  expect(suggest(known, "   ")).toEqual({ known: [], typed: null });
});

test("what goes with an item is its quantity and its note", () => {
  expect(itemDetail({ quantity: "2", note: "lactose-free" })).toBe("2 · lactose-free");
  expect(itemDetail({ quantity: null, note: null })).toBeUndefined();
});

test("a product says its habit, or how many times while it has none", () => {
  expect(habitDetail(english, { every: "every week", since: "9 days ago", times: 5 })).toBe("every week · 9 days ago");
  expect(habitDetail(english, { every: null, since: "yesterday", times: 1 })).toBe("once · yesterday");
  expect(habitDetail(english, { every: null, since: null, times: 2 })).toBe("2 times");
  expect(habitDetail(spanish, { every: null, since: null, times: 2 })).toBe(spanish("habit.times", { count: 2 }));
});

test("built-in sections are named in the person's language, their own sections as written", () => {
  expect(sectionName(english, "dairy", "Dairy and eggs")).toBe("Dairy and eggs");
  expect(sectionName(spanish, "dairy", "Dairy and eggs")).toBe(spanish("section.dairy"));
  expect(sectionName(spanish, "garage", "Garage")).toBe("Garage");
});

test("a trip is named by its day, in the person's time zone and language", () => {
  configureRegional({ locale: "en-US", timeZone: "Europe/Madrid" });
  try {
    expect(dayLabel("2026-09-22T21:30:00Z")).toMatch(/Tuesday.*September.*22|Tuesday, 22 September/);
    configureRegional({ timeZone: "America/New_York" });
    expect(dayLabel("2026-09-22T03:30:00Z")).toMatch(/Monday/);
  } finally {
    configureRegional({ locale: "es-ES", timeZone: "Europe/Madrid" });
  }
});

describe("what is painted before the server answers", () => {
  const item = (id: string, category_id: string, in_cart = false): Item => ({
    id,
    product_id: id,
    name: id,
    category_id,
    quantity: null,
    note: null,
    in_cart,
    source: "app",
  });
  const list: ShoppingList = {
    groups: [
      { category_id: "dairy", name: "Dairy", emoji: "🥛", items: [item("milk", "dairy"), item("yogurt", "dairy")] },
      { category_id: "bakery", name: "Bakery", emoji: "🥖", items: [item("bread", "bakery")] },
    ],
    cart: [item("eggs", "dairy", true)],
    due: [],
    usual: [],
    pending: 3,
    in_cart: 1,
    space_id: null,
  };

  it("into the trolley: it leaves its section, which goes if empty, and counts are redone", () => {
    const moved = withCart(list, "bread", true);
    expect(moved.groups.map((group) => group.category_id)).toEqual(["dairy"]);
    expect(moved.cart.map((one) => [one.id, one.in_cart])).toEqual([
      ["eggs", true],
      ["bread", true],
    ]);
    expect([moved.pending, moved.in_cart]).toEqual([2, 2]);
  });

  it("out of the trolley: back to its section; if it is not there, it is not guessed", () => {
    const back = withCart(list, "eggs", false);
    expect(back.groups[0]!.items.map((one) => one.id)).toEqual(["milk", "yogurt", "eggs"]);
    expect([back.pending, back.in_cart]).toEqual([4, 0]);
    const orphan = { ...list, cart: [item("fish", "fish", true)] };
    expect(withCart(orphan, "fish", false)).toBe(orphan);
  });

  it("removing something takes it out wherever it is", () => {
    expect([without(list, "milk").pending, without(list, "eggs").in_cart]).toEqual([2, 0]);
  });
});

describe("offline, the list as the server will leave it", () => {
  const empty: ShoppingList = { groups: [], cart: [], due: [], usual: [], pending: 0, in_cart: 0, space_id: null };
  const sections = [
    { id: "bakery", name: "Bakery", emoji: "🥖", position: 2 },
    { id: "dairy", name: "Dairy", emoji: "🥛", position: 3 },
    { id: "other", name: "Other", emoji: "📦", position: 9 },
  ];

  it("an item goes to the section it already has, or to Other, and what is on the list is not repeated", () => {
    let list = withAdded(
      empty,
      { id: "1", name: "milk", quantity: null },
      [product("Milk", { category_id: "dairy", quantity: "2" })],
      sections,
    );
    list = withAdded(list, { id: "2", name: "Odd thing", quantity: null }, [], sections);
    list = withAdded(list, { id: "3", name: "Bread", quantity: null }, [product("Bread", { category_id: "bakery" })], sections);
    list = withAdded(list, { id: "4", name: "MILK", quantity: null }, [], sections);

    expect(list.groups.map((group) => [group.category_id, group.items.map((one) => one.name)])).toEqual([
      ["bakery", ["Bread"]],
      ["dairy", ["Milk"]],
      ["other", ["Odd thing"]],
    ]);
    expect(list.groups[1]!.items[0]).toMatchObject({ id: "1", quantity: "2" });
    expect(list.pending).toBe(3);
  });

  it("editing and finishing", () => {
    const one = withAdded(empty, { id: "1", name: "Bread", quantity: null }, [], sections);
    expect(withEdited(one, "1", "2", "wholemeal").groups[0]!.items[0]).toMatchObject({ quantity: "2", note: "wholemeal" });
    const carted = withCart(one, "1", true);
    expect(withFinished(carted)).toMatchObject({ cart: [], in_cart: 0, groups: [] });
  });
});

describe("changing section offline", () => {
  it("moves to the other section and leaves its own if it is left empty", () => {
    const sections = [
      { id: "bakery", name: "Bakery", emoji: "🥖", position: 2 },
      { id: "dairy", name: "Dairy", emoji: "🥛", position: 3 },
    ];
    const empty: ShoppingList = { groups: [], cart: [], due: [], usual: [], pending: 0, in_cart: 0, space_id: null };
    const one = withAdded(empty, { id: "1", name: "Kefir", quantity: null }, [product("Kefir", { category_id: "bakery" })], sections);
    const moved = withSection(one, "1", "dairy", sections);
    expect(moved.groups.map((group) => [group.category_id, group.items.map((item) => item.name)])).toEqual([["dairy", ["Kefir"]]]);
    expect(moved.pending).toBe(1);
  });
});

describe("the redesign", () => {
  it("days since the last purchase, by the calendar", () => {
    expect(daysSince("2026-10-15", "2026-10-30")).toBe(15);
    expect(daysSince("2026-10-30", "2026-10-30")).toBe(0);
    expect(daysSince(null, "2026-10-30")).toBeNull();
    expect(daysSince("2026-10-24", "2026-10-26")).toBe(2);
  });

  it("the trolley in one line", () => {
    expect(cartLine(english, [])).toBe("");
    expect(cartLine(english, ["Bread"])).toBe("Bread");
    expect(cartLine(english, ["Bread", "Milk"])).toBe("Bread and Milk");
    expect(cartLine(english, ["Bread", "Bananas", "Oil", "Eggs"])).toBe("Bread, bananas and 2 more");
    expect(cartLine(spanish, ["Bread", "Milk"])).toBe(spanish("cart.two", { first: "Bread", second: "Milk" }));
  });
});
