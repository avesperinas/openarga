import { renderToString } from "react-dom/server";

import { route } from "./App";
import type { Added, Category } from "./api";
import { summary } from "./History";
import { english, inLocale, spanish } from "./i18n/testing";
import { noticeFor, ShoppingScreen } from "./Shopping";

const CATEGORIES: Category[] = [{ id: "other", name: "Other", emoji: "🛒", position: 13 }];

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

test("what lands in Other is said, because it asks you to change its section", () => {
  const notice = noticeFor(english, [added("Odd thing", { category_id: "other" }), added("Milk")], CATEGORIES);

  expect(notice).toContain("Odd thing goes in Other");
  expect(noticeFor(spanish, [added("Odd thing", { category_id: "other" })], CATEGORIES)).toContain(
    spanish("section.other"),
  );
});

test("what was already on the list is said; the usual is not announced", () => {
  expect(noticeFor(english, [added("Milk", { already_on_list: true })], CATEGORIES)).toBe(
    "Milk was already on the list.",
  );
  expect(noticeFor(english, [added("Milk")], CATEGORIES)).toBe("");
  expect(noticeFor(english, [added("Gift", { category_id: "other", guessed: false })], CATEGORIES)).toBe("");
});

test("a product without three purchases says how often is not known yet", () => {
  expect(summary(english, { times: 2, since: "yesterday", every: null })).toBe(
    "Bought 2 times, last yesterday. With three purchases it will be known how often you buy it.",
  );
  expect(summary(english, { times: 5, since: "3 days ago", every: "every week" })).toBe(
    "Bought 5 times, last 3 days ago. You buy it every week.",
  );
});

test("each tab has its address", () => {
  expect(route("/shopping/")).toBe("list");
  expect(route("/shopping")).toBe("list");
  expect(route("/shopping/history/")).toBe("history");
  expect(route("/shopping/settings")).toBe("settings");
});

test("the empty screen paints without breaking before it has data", () => {
  expect(renderToString(inLocale(<ShoppingScreen />))).toContain(english("add.label"));
});
