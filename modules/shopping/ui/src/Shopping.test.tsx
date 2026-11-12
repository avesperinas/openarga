import { renderToString } from "react-dom/server";

import { route } from "./App";
import type { Added, Category } from "./api";
import { summary } from "./History";
import { noticeFor, ShoppingScreen } from "./Shopping";

const CATEGORIES: Category[] = [{ id: "other", name: "Otros", emoji: "🛒", position: 13 }];

function added(name: string, extra: Partial<Added> = {}): Added {
  return {
    item_id: name,
    product_id: name,
    name,
    category_id: "dairy",
    new_product: true,
    already_on_list: false,
    guessed: true,
    ...extra,
  };
}

test("lo que cae en Otros se dice, porque pide que le cambies la sección", () => {
  const notice = noticeFor([added("Cosa rara", { category_id: "other" }), added("Leche")], CATEGORIES);

  expect(notice).toContain("Cosa rara va en Otros");
});

test("lo que ya estaba apuntado se dice; lo normal no se anuncia", () => {
  expect(noticeFor([added("Leche", { already_on_list: true })], CATEGORIES)).toBe("Leche ya estaba apuntado.");
  expect(noticeFor([added("Leche")], CATEGORIES)).toBe("");
  expect(noticeFor([added("Regalo", { category_id: "other", guessed: false })], CATEGORIES)).toBe("");
});

test("un producto sin tres compras dice que aún no se sabe cada cuánto", () => {
  expect(summary({ times: 2, since: "ayer", every: null })).toBe(
    "Comprado 2 veces, la última ayer. Con tres compras se sabrá cada cuánto lo compras.",
  );
  expect(summary({ times: 5, since: "hace 3 días", every: "cada semana" })).toBe(
    "Comprado 5 veces, la última hace 3 días. Lo compras cada semana.",
  );
});

test("cada pestaña tiene su dirección", () => {
  expect(route("/shopping/")).toBe("list");
  expect(route("/shopping")).toBe("list");
  expect(route("/shopping/historial/")).toBe("history");
});

test("la pantalla vacía se pinta sin romperse antes de tener datos", () => {

  expect(renderToString(<ShoppingScreen />)).toContain("Apuntar");
});
