import type { Item, Product, ShoppingList } from "./api";
import {
  cartLine,
  daysSince,
  dayLabel,
  fold,
  habitDetail,
  itemDetail,
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

test("compara como el servidor: sin tildes, sin mayúsculas y sin espacios de más", () => {
  expect(fold("  PLÁTANOS   de Canarias ")).toBe("platanos de canarias");
  expect(fold("Piña")).toBe("pina");
});

test("lo escrito es el principio de alguna palabra", () => {
  expect(startsAWord("plat", "Plátanos")).toBe(true);
  expect(startsAWord("plat", "Papel de plata")).toBe(true);
  expect(startsAWord("plat", "Espátula")).toBe(false);
  expect(startsAWord("  ", "Plátanos")).toBe(false);
});

test("al escribir se ofrece lo que ya compras y, si no es ninguno, apuntarlo tal cual", () => {
  const known = [product("Plátanos", { times: 5 }), product("Papel de plata", { times: 1 })];

  expect(suggest(known, "plat").known.map((one) => one.name)).toEqual(["Plátanos", "Papel de plata"]);
  expect(suggest(known, "plat").typed).toBe("plat");
  expect(suggest(known, "platanos").typed).toBeNull();
  expect(suggest(known, "   ")).toEqual({ known: [], typed: null });
});

test("lo que acompaña a lo apuntado es su cantidad y su nota", () => {
  expect(itemDetail({ quantity: "2", note: "sin lactosa" })).toBe("2 · sin lactosa");
  expect(itemDetail({ quantity: null, note: null })).toBeUndefined();
});

test("de un producto se dice su costumbre, o cuántas veces si aún no la tiene", () => {
  expect(habitDetail({ every: "cada semana", since: "hace 9 días", times: 5 })).toBe(
    "cada semana · hace 9 días",
  );
  expect(habitDetail({ every: null, since: "ayer", times: 1 })).toBe("1 vez · ayer");
  expect(habitDetail({ every: null, since: null, times: 2 })).toBe("2 veces");
});

test("una compra se nombra por su día, en la hora de Madrid", () => {
  expect(dayLabel("2026-09-22T21:30:00Z")).toBe("Martes, 22 de septiembre");
});

describe("lo que se pinta antes de que conteste", () => {
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
      { category_id: "dairy", name: "Lácteos", emoji: "🥛", items: [item("leche", "dairy"), item("yogur", "dairy")] },
      { category_id: "bakery", name: "Panadería", emoji: "🥖", items: [item("pan", "bakery")] },
    ],
    cart: [item("huevos", "dairy", true)],
    due: [],
    usual: [],
    pending: 3,
    in_cart: 1,
    space_id: null,
  };

  it("al carro: sale de su sección, que desaparece si se queda vacía, y se recuentan", () => {
    const moved = withCart(list, "pan", true);
    expect(moved.groups.map((group) => group.category_id)).toEqual(["dairy"]);
    expect(moved.cart.map((one) => [one.id, one.in_cart])).toEqual([
      ["huevos", true],
      ["pan", true],
    ]);
    expect([moved.pending, moved.in_cart]).toEqual([2, 2]);
  });

  it("fuera del carro: vuelve a su sección; si no está, no se adivina", () => {
    const back = withCart(list, "huevos", false);
    expect(back.groups[0]!.items.map((one) => one.id)).toEqual(["leche", "yogur", "huevos"]);
    expect([back.pending, back.in_cart]).toEqual([4, 0]);
    const orphan = { ...list, cart: [item("pescado", "fish", true)] };
    expect(withCart(orphan, "pescado", false)).toBe(orphan);
  });

  it("quitar algo lo saca de donde esté", () => {
    expect([without(list, "leche").pending, without(list, "huevos").in_cart]).toEqual([2, 0]);
  });
});

describe("sin red, la lista como la dejará el servidor", () => {
  const empty: ShoppingList = { groups: [], cart: [], due: [], usual: [], pending: 0, in_cart: 0, space_id: null };
  const sections = [
    { id: "bakery", name: "Panadería", emoji: "🥖", position: 2 },
    { id: "dairy", name: "Lácteos", emoji: "🥛", position: 3 },
    { id: "other", name: "Otros", emoji: "📦", position: 9 },
  ];

  it("lo apuntado va a la sección que ya tiene, o a Otros, y lo ya apuntado no se repite", () => {
    let list = withAdded(empty, { id: "1", name: "leche", quantity: null }, [product("Leche", { category_id: "dairy", quantity: "2" })], sections);
    list = withAdded(list, { id: "2", name: "Cosa rara", quantity: null }, [], sections);
    list = withAdded(list, { id: "3", name: "Pan", quantity: null }, [product("Pan", { category_id: "bakery" })], sections);
    list = withAdded(list, { id: "4", name: "LECHE", quantity: null }, [], sections);

    expect(list.groups.map((group) => [group.category_id, group.items.map((one) => one.name)])).toEqual([
      ["bakery", ["Pan"]],
      ["dairy", ["Leche"]],
      ["other", ["Cosa rara"]],
    ]);
    expect(list.groups[1]!.items[0]).toMatchObject({ id: "1", quantity: "2" });
    expect(list.pending).toBe(3);
  });

  it("cambiar y terminar", () => {
    const one = withAdded(empty, { id: "1", name: "Pan", quantity: null }, [], sections);
    expect(withEdited(one, "1", "2", "integral").groups[0]!.items[0]).toMatchObject({ quantity: "2", note: "integral" });
    const carted = withCart(one, "1", true);
    expect(withFinished(carted)).toMatchObject({ cart: [], in_cart: 0, groups: [] });
  });
});

describe("cambiar de sección sin red", () => {
  it("pasa a la otra sección y deja la suya si se queda vacía", () => {
    const sections = [
      { id: "bakery", name: "Panadería", emoji: "🥖", position: 2 },
      { id: "dairy", name: "Lácteos", emoji: "🥛", position: 3 },
    ];
    const empty: ShoppingList = { groups: [], cart: [], due: [], usual: [], pending: 0, in_cart: 0, space_id: null };
    const one = withAdded(empty, { id: "1", name: "Kéfir", quantity: null }, [product("Kéfir", { category_id: "bakery" })], sections);
    const moved = withSection(one, "1", "dairy", sections);
    expect(moved.groups.map((group) => [group.category_id, group.items.map((item) => item.name)])).toEqual([["dairy", ["Kéfir"]]]);
    expect(moved.pending).toBe(1);
  });
});

describe("el rediseño (T-B13)", () => {
  it("los días desde la última compra, por el calendario", () => {
    expect(daysSince("2026-10-15", "2026-10-30")).toBe(15);
    expect(daysSince("2026-10-30", "2026-10-30")).toBe(0);
    expect(daysSince(null, "2026-10-30")).toBeNull();
    expect(daysSince("2026-10-24", "2026-10-26")).toBe(2);
  });

  it("lo del carro en una línea", () => {
    expect(cartLine([])).toBe("");
    expect(cartLine(["Pan"])).toBe("Pan");
    expect(cartLine(["Pan", "Leche"])).toBe("Pan y Leche");
    expect(cartLine(["Pan", "Plátanos", "Aceite", "Huevos"])).toBe("Pan, plátanos y 2 más");
  });
});
