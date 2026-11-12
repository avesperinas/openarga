import {
  Button,
  CheckRow,
  ChoiceChips,
  DockBar,
  EmptyState,
  ErrorState,
  GroupLabel,
  Hint,
  Inline,
  List,
  ListRow,
  Notice,
  OfflineNotice,
  PullToRefresh,
  Screen,
  Section,
  Sheet,
  Skeleton,
  SwipeRow,
  TextField,
  useToast,
} from "@openarga/ui";
import { invalidate, mutate, peek, useResource } from "@openarga/app";
import { useOfflineQueue } from "@openarga/app/offline";
import { useCallback, useMemo, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Added,
  type Category,
  type Item,
  type ShoppingList,
  Queued,
  Unauthorised,
  addItems,
  chooseList,
  dropItem,
  finishTrip,
  newId,
  queue,
  readCategories,
  readList,
  readProducts,
  readSpaces,
  setCategory,
  setInCart,
  signIn,
  updateItem,
} from "./api";
import { ScreenHeader } from "./Header";
import { ListPicker } from "./ListPicker";
import {
  cartLine,
  habitDetail,
  itemDetail,
  suggest,
  withAdded,
  withCart,
  withEdited,
  withFinished,
  withSection,
  without,
} from "./words";

const SHOWN = 8;

export function ShoppingScreen() {
  const listed = useResource(
    "list",
    () => {
      const shown = peek<ShoppingList>("list");
      return queue.state().pending > 0 && shown ? Promise.resolve(shown) : readList();
    },
    { persist: true },
  );
  const list = listed.data ?? null;
  const productsRead = useResource("products", () => readProducts(), { persist: true });
  const products = productsRead.data ?? [];
  const toast = useToast();
  const categories = useResource("categories", readCategories, { staleMs: 86_400_000, persist: true }).data ?? [];
  const known = useResource("kernel:spaces", () =>
    readSpaces().catch((error: unknown) => {
      throw error instanceof Unauthorised ? new Error("sin espacios") : error;
    }),
  );
  const spaces = known.error ? null : (known.data ?? null);
  const [query, setQuery] = useState("");
  const [problem, setProblem] = useState("");
  const [notice, setNotice] = useState("");
  const [open, setOpen] = useState<Item | null>(null);
  const [finishing, setFinishing] = useState(false);
  const offline = useOfflineQueue(queue);

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
  }, []);

  function change(optimistic: (now: ShoppingList) => ShoppingList, action: () => Promise<ShoppingList>) {
    setProblem("");
    void mutate<ShoppingList>("list", (now) => (now ? optimistic(now) : (now as never)), { request: action }).catch(
      fail,
    );
  }

  async function add(name: string, quantity?: string | null) {
    setProblem("");
    setNotice("");
    const id = newId();
    try {
      const { added, list: fresh } = await addItems([{ id, name, quantity: quantity ?? null }]);
      await mutate("list", fresh);
      setNotice(noticeFor(added, categories));
      invalidate("products");
    } catch (error) {
      if (!(error instanceof Queued)) return fail(error);
      await mutate<ShoppingList>("list", (now) =>
        now ? withAdded(now, { id, name, quantity: quantity ?? null }, products, categories) : (now as never),
      );
    }
    setQuery("");
  }

  const offered = useMemo(() => suggest(products, query), [products, query]);
  const typed = offered.typed;
  const empty = list !== null && list.pending === 0 && list.in_cart === 0;
  const [more, setMore] = useState(false);
  const due = useMemo(() => new Set((list?.due ?? []).map((one) => one.id)), [list]);
  const suggestions = useMemo(() => {
    if (!list) return [];
    const seen = new Set<string>();
    return [...list.due, ...list.usual].filter((one) => !seen.has(one.id) && Boolean(seen.add(one.id)));
  }, [list]);

  function remove(item: Item) {
    setProblem("");
    const dropped = mutate<ShoppingList>("list", (now) => (now ? without(now, item.id) : (now as never)), {
      request: () => dropItem(item),
    });
    dropped.catch(fail);
    toast({
      message: `Quitado · ${item.name}`,
      action: {
        label: "Deshacer",
        run: () =>
          void dropped
            .then(() => add(item.name, item.quantity))
            .catch(fail),
      },
    });
  }

  return (
    <Screen>
      <PullToRefresh onRefresh={() => Promise.all([listed.refresh(), productsRead.refresh()])}>
        <ScreenHeader title="La compra" />
        <OfflineNotice pending={offline.pending} />
        {offline.signedOut && (
          <Notice tone="warning" title="Sin sesión">
            Inicia sesión para enviar lo apuntado sin conexión.{" "}
            <Button variant="plain" onClick={signIn}>
              Entrar
            </Button>
          </Notice>
        )}
        {offline.refused.map((one) => (
          <Notice key={one.key} tone="negative" title={`No se pudo guardar: ${one.what}`}>
            {one.problem}{" "}
            <Button variant="plain" onClick={() => void offline.retry(one.key!)}>
              Reintentar
            </Button>
            <Button variant="plain" onClick={() => void offline.dismiss(one.key!)}>
              Olvidarlo
            </Button>
          </Notice>
        ))}

        {list && spaces && (
          <ListPicker
            list={list}
            spaces={spaces}
            onChoose={async (spaceId) => {
              setProblem("");
              try {
                await mutate("list", await chooseList(spaceId));
                invalidate("products");
                invalidate("trips");
              } catch (error) {
                fail(error);
              }
            }}
          />
        )}

        <TextField
          label="Apuntar"
          type="search"
          value={query}
          onChange={setQuery}
          placeholder="leche, pan, detergente…"
          onSubmit={() => query.trim() && void add(query.trim())}
        />

        {problem && (
          <Hint tone="warning">
            {problem}
          </Hint>
        )}
        {notice && <Hint>{notice}</Hint>}

        {query.trim() && (
          <List>
            {typed && <ListRow title={`Apuntar «${typed}»`} accessory="plus" onClick={() => void add(typed)} />}
            {offered.known.map((product) => (
              <ListRow
                key={product.id}
                title={product.name}
                detail={product.on_list ? "ya apuntado" : habitDetail(product)}
                accessory={product.on_list ? "done" : "plus"}
                disabled={product.on_list}
                onClick={() => void add(product.name)}
              />
            ))}
          </List>
        )}

        {listed.error && list === null && (
          <ErrorState title="No se ha podido leer la lista" detail={listed.error.message} onRetry={listed.refresh} />
        )}
        {listed.loading && <Skeleton label="Cargando la lista" />}

        {list && !query.trim() && suggestions.length > 0 && (
          <Section title="Te puede faltar">
            <Inline label="Te puede faltar" scroll="narrow" maxRows={2}>
              {suggestions.slice(0, SHOWN).map((product) => (
                <Button
                  key={product.id}
                  size="small"
                  variant="tinted"
                  icon={due.has(product.id) ? "clock" : "plus"}
                  aria-label={`Apuntar ${product.name}, ${habitDetail(product)}${due.has(product.id) ? ", te toca" : ""}`}
                  onClick={() => void add(product.name)}
                >
                  {product.name}
                </Button>
              ))}
              {suggestions.length > SHOWN && (
                <Button size="small" variant="plain" onClick={() => setMore(true)}>
                  {`Más (${suggestions.length})`}
                </Button>
              )}
            </Inline>
          </Section>
        )}
        {more && list && (
          <Sheet title="Te puede faltar" onClose={() => setMore(false)}>
            {[
              { title: "Te toca", items: list.due },
              { title: "Lo de siempre", items: list.usual.filter((one) => !due.has(one.id)) },
            ]
              .filter((group) => group.items.length > 0)
              .map((group) => (
                <section key={group.title} className="shopping-more">
                  <GroupLabel count={group.items.length}>{group.title}</GroupLabel>
                  <List>
                    {group.items.map((product) => (
                      <ListRow
                        key={product.id}
                        title={product.name}
                        subtitle={habitDetail(product)}
                        action={{ icon: "plus", label: `Apuntar ${product.name}`, onClick: () => void add(product.name) }}
                      />
                    ))}
                  </List>
                </section>
              ))}
          </Sheet>
        )}

        {empty && (
          <EmptyState
            icon="basket"
            title="No hay nada apuntado"
            action={{
              label: "Apuntar algo",
              icon: "plus",
              onClick: () => document.querySelector<HTMLInputElement>(".text-field input")?.focus(),
            }}
          >
            Escribe arriba lo que haga falta. Cada compra que termines se guarda, y de ahí sale lo que te toca
            comprar antes de que se acabe.
          </EmptyState>
        )}

        {list?.groups.map((group) => (
          <Section key={group.category_id} title={`${group.emoji} ${group.name}`}>
            <List>
              {group.items.map((item) => (
                <SwipeRow
                  key={item.id}
                  label={item.name}
                  actions={[{ label: "Quitar", icon: "trash", tone: "danger", onAction: () => remove(item) }]}
                >
                  <CheckRow
                    title={item.name}
                    detail={itemDetail(item)}
                    checked={false}
                    onToggle={() => change((now) => withCart(now, item.id, true), () => setInCart(item, true))}
                    more={{ label: `Cambiar ${item.name}`, onClick: () => setOpen(item) }}
                  />
                </SwipeRow>
              ))}
            </List>
          </Section>
        ))}

        {list && list.cart.length > 0 && (
          <Section title="En el carro" count={list.in_cart}>
            <List>
              {list.cart.map((item) => (
                <CheckRow
                  key={item.id}
                  title={item.name}
                  detail={itemDetail(item)}
                  checked
                  onToggle={() => change((now) => withCart(now, item.id, false), () => setInCart(item, false))}
                />
              ))}
            </List>
          </Section>
        )}

        {list && list.in_cart > 0 && !finishing && (
          <DockBar
            title={list.in_cart === 1 ? "1 en el carro" : `${list.in_cart} en el carro`}
            detail={cartLine(list.cart.map((item) => item.name))}
            action={{ label: "Terminar", icon: "done", onClick: () => setFinishing(true) }}
          />
        )}

        {open && (
          <ItemSheet
            item={open}
            categories={categories}
            onClose={() => setOpen(null)}
            onSaved={(fresh) => {
              void mutate<ShoppingList>("list", fresh);
              setOpen(null);
            }}
          />
        )}
        {finishing && list && (
          <FinishSheet
            list={list}
            onClose={() => setFinishing(false)}
            onFinished={(fresh, queued) => {
              void mutate<ShoppingList>("list", fresh);
              setFinishing(false);
              setNotice(
                queued
                  ? "Compra guardada en el móvil: se envía al volver la red."
                  : "Compra guardada. Lo que no cogiste sigue en la lista.",
              );
              invalidate("products");
              invalidate("trips");
            }}
          />
        )}
        <AppVersion />
      </PullToRefresh>
    </Screen>
  );
}

export function noticeFor(added: Added[], categories: Category[]): string {
  const other = added.filter((one) => one.guessed && one.category_id === "other");
  if (other.length) {
    const where = categories.find((one) => one.id === "other")?.name ?? "Otros";
    return `${other.map((one) => one.name).join(", ")} va en ${where}: tócalo en la lista para cambiarle la sección.`;
  }
  const already = added.filter((one) => one.already_on_list);
  if (already.length) return `${already.map((one) => one.name).join(", ")} ya estaba apuntado.`;
  return "";
}

function ItemSheet({
  item,
  categories,
  onClose,
  onSaved,
}: {
  item: Item;
  categories: Category[];
  onClose: () => void;
  onSaved: (list: ShoppingList | ((now: ShoppingList | undefined) => ShoppingList)) => void;
}) {
  const [quantity, setQuantity] = useState(item.quantity ?? "");
  const [note, setNote] = useState(item.note ?? "");
  const [category, setCategoryId] = useState(item.category_id);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function run(action: () => Promise<ShoppingList>, offline: (now: ShoppingList) => ShoppingList) {
    setBusy(true);
    setProblem("");
    try {
      onSaved(await action());
    } catch (error) {
      if (error instanceof Queued) return onSaved((now) => (now ? offline(now) : (now as never)));
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    let fresh: ShoppingList | undefined;
    let queued = false;
    const writes = [() => updateItem(item, quantity.trim() || null, note.trim() || null)];
    if (category !== item.category_id) writes.push(() => setCategory(item.product_id, category, item.name));
    for (const write of writes) {
      try {
        fresh = await write();
      } catch (error) {
        if (!(error instanceof Queued)) throw error;
        queued = true;
      }
    }
    if (queued) throw new Queued();
    return fresh!;
  }
  const provisional = item.product_id === item.id;

  return (
    <Sheet
      title={item.name}
      onClose={onClose}
      action={{
        label: busy ? "Guardando…" : "Guardar",
        onClick: () =>
          void run(save, (now) =>
            withSection(withEdited(now, item.id, quantity.trim() || null, note.trim() || null), item.id, category, categories),
          ),
        disabled: busy,
      }}
    >
      <TextField label="Cantidad" value={quantity} onChange={setQuantity} placeholder="2, 1 kg, pack de 6" />
      <TextField label="Nota" value={note} onChange={setNote} placeholder="la sin lactosa" />
      {provisional ? (
        <Hint>Apuntado sin conexión: la sección se podrá cambiar cuando se envíe.</Hint>
      ) : (
        <ChoiceChips
          label="Sección"
          value={category}
          onChange={setCategoryId}
          options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${one.name}` }))}
        />
      )}
      {item.source === "tool" && <Hint>Lo apuntó Claude.</Hint>}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Button block disabled={busy} onClick={() => void run(() => dropItem(item), (now) => without(now, item.id))}>
        Quitar de la lista
      </Button>
      <Hint>Quitarlo no borra nada: sigue en tu historial.</Hint>
    </Sheet>
  );
}

function FinishSheet({
  list,
  onClose,
  onFinished,
}: {
  list: ShoppingList;
  onClose: () => void;
  onFinished: (list: ShoppingList, queued: boolean) => void;
}) {
  const count = list.in_cart;
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function finish() {
    setBusy(true);
    setProblem("");
    try {
      onFinished((await finishTrip()).list, false);
    } catch (error) {
      if (error instanceof Queued) return onFinished(withFinished(list), true);
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : "No se pudo guardar la compra.");
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Terminar la compra"
      onClose={onClose}
      action={{ label: busy ? "Guardando…" : "Terminar la compra", onClick: () => void finish(), disabled: busy }}
    >
      <GroupLabel>Te llevas · {count}</GroupLabel>
      <List>
        {list.cart.map((item) => (
          <ListRow key={item.id} title={item.name} detail={itemDetail(item)} accessory="done" />
        ))}
      </List>
      {list.pending > 0 && (
        <>
          <GroupLabel>Se quedan para la próxima · {list.pending}</GroupLabel>
          <List>
            {list.groups.flatMap((group) => group.items).map((item) => (
              <ListRow key={item.id} title={item.name} detail={itemDetail(item)} />
            ))}
          </List>
        </>
      )}
      <Hint>
        Se guarda{count === 1 ? " lo" : `n los ${count} productos`} que llevas en el carro, con la fecha de hoy.
        Lo que no has cogido se queda en la lista para la próxima.
      </Hint>
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
    </Sheet>
  );
}
