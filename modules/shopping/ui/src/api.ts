import { createApi, invalidate } from "@openarga/app";
import { createOfflineQueue } from "@openarga/app/offline";

export { Unauthorised, signIn } from "@openarga/app";
export { NeedsNetwork, Queued } from "@openarga/app/offline";

export const api = createApi("shopping");
const { get } = api;

export const queue = createOfflineQueue({ app: "shopping" });
queue.onSent(() => {
  invalidate("list");
  invalidate("products");
  invalidate("trips");
});

const send = <T>(path: string, method: string, body?: unknown, what?: string, repeatable?: boolean) =>
  queue.send<T>(`${api.base}${path}`, method, body, { what, repeatable });

export const newId = (): string => crypto.randomUUID();

export interface Category {
  id: string;
  name: string;
  emoji: string;
  position: number;
}

export interface Item {
  id: string;
  product_id: string;
  name: string;
  category_id: string;
  quantity: string | null;
  note: string | null;
  in_cart: boolean;
  source: string;
}

export interface Group {
  category_id: string;
  name: string;
  emoji: string;
  items: Item[];
}

export interface Product {
  id: string;
  name: string;
  category_id: string;
  quantity: string | null;
  times: number;
  last: string | null;
  every_days: number | null;
  every: string | null;
  since: string | null;
  due: boolean;
  on_list: boolean;
}

export interface ShoppingList {
  groups: Group[];
  cart: Item[];
  due: Product[];
  usual: Product[];
  pending: number;
  in_cart: number;
  space_id: string | null;
}

export interface Space {
  id: string;
  name: string;
  me: string;
  members: { user_id: string; name: string | null }[];
}

export interface Entry {
  id?: string;
  name: string;
  quantity?: string | null;
  note?: string | null;
  category_id?: string | null;
}

export interface Added {
  item_id: string;
  product_id: string;
  name: string;
  category_id: string;
  new_product: boolean;
  already_on_list: boolean;
  guessed: boolean;
}

export interface TripProduct {
  name: string;
  category_id: string;
  quantity: string | null;
}

export interface Trip {
  id: string;
  finished_at: string;
  items: number;
  products: TripProduct[];
}

export const readCategories = () => get<Category[]>("/categories");
export const readList = () => get<ShoppingList>("/list");
export const readProducts = (query?: string) =>
  get<Product[]>(`/products${query ? `?query=${encodeURIComponent(query)}` : ""}`);
export const readTrips = () => get<Trip[]>("/trips");

export const addItems = (items: Entry[]) =>
  send<{ added: Added[]; list: ShoppingList }>(
    "/list/items",
    "POST",
    { items: items.map((one) => ({ ...one, id: one.id ?? newId() })) },
    items.map((one) => one.name).join(", "),
  );
export const setInCart = (item: Pick<Item, "id" | "name">, inCart: boolean) =>
  send<ShoppingList>(`/list/items/${item.id}/cart`, "PUT", { in_cart: inCart }, `marcar ${item.name}`);
export const updateItem = (item: Pick<Item, "id" | "name">, quantity: string | null, note: string | null) =>
  send<ShoppingList>(`/list/items/${item.id}`, "PUT", { quantity, note }, `cambiar ${item.name}`);
export const dropItem = (item: Pick<Item, "id" | "name">) =>
  send<ShoppingList>(`/list/items/${item.id}/drop`, "POST", undefined, `quitar ${item.name}`, true);
export const setCategory = (productId: string, categoryId: string, name: string) =>
  send<ShoppingList>(`/products/${productId}/category`, "PUT", { category_id: categoryId }, `la sección de ${name}`);
export const chooseList = (spaceId: string | null) =>
  send<ShoppingList>("/list/owner", "PUT", { space_id: spaceId }, "cambiar de lista", false);
export const readSpaces = () => api.raw<Space[]>("/api/kernel/spaces");
export const finishTrip = (id: string = newId()) =>
  send<{ trip: Trip; list: ShoppingList }>("/list/finish", "POST", { id }, "terminar la compra");

export const readVersion = api.readVersion;
