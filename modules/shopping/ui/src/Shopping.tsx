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
  type Translate,
  useT,
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
  sectionName,
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
  const t = useT();
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
      throw error instanceof Unauthorised ? new Error("no spaces") : error;
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
    setProblem(error instanceof Error ? error.message : t("common.save_failed"));
  }, [t]);

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
      setNotice(noticeFor(t, added, categories));
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
      message: t("removed.toast", { name: item.name }),
      action: {
        label: t("removed.undo"),
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
        <ScreenHeader title={t("list.title")} />
        <OfflineNotice pending={offline.pending} />
        {offline.signedOut && (
          <Notice tone="warning" title={t("offline.signed_out")}>
            {t("offline.sign_in_body")}{" "}
            <Button variant="plain" onClick={signIn}>
              {t("offline.sign_in")}
            </Button>
          </Notice>
        )}
        {offline.refused.map((one) => (
          <Notice key={one.key} tone="negative" title={t("offline.refused", { what: one.what ?? "" })}>
            {one.problem}{" "}
            <Button variant="plain" onClick={() => void offline.retry(one.key!)}>
              {t("offline.retry")}
            </Button>
            <Button variant="plain" onClick={() => void offline.dismiss(one.key!)}>
              {t("offline.forget")}
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
          label={t("add.label")}
          type="search"
          value={query}
          onChange={setQuery}
          placeholder={t("add.placeholder")}
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
            {typed && <ListRow title={t("add.typed", { name: typed })} accessory="plus" onClick={() => void add(typed)} />}
            {offered.known.map((product) => (
              <ListRow
                key={product.id}
                title={product.name}
                detail={product.on_list ? t("add.already") : habitDetail(t, product)}
                accessory={product.on_list ? "done" : "plus"}
                disabled={product.on_list}
                onClick={() => void add(product.name)}
              />
            ))}
          </List>
        )}

        {listed.error && list === null && (
          <ErrorState title={t("list.read_failed")} detail={listed.error.message} onRetry={listed.refresh} />
        )}
        {listed.loading && <Skeleton label={t("list.loading")} />}

        {list && !query.trim() && suggestions.length > 0 && (
          <Section title={t("suggest.title")}>
            <Inline label={t("suggest.title")} scroll="narrow" maxRows={2}>
              {suggestions.slice(0, SHOWN).map((product) => (
                <Button
                  key={product.id}
                  size="small"
                  variant="tinted"
                  icon={due.has(product.id) ? "clock" : "plus"}
                  aria-label={t(due.has(product.id) ? "suggest.add_aria_due" : "suggest.add_aria", {
                    name: product.name,
                    detail: habitDetail(t, product),
                  })}
                  onClick={() => void add(product.name)}
                >
                  {product.name}
                </Button>
              ))}
              {suggestions.length > SHOWN && (
                <Button size="small" variant="plain" onClick={() => setMore(true)}>
                  {t("suggest.more", { count: suggestions.length })}
                </Button>
              )}
            </Inline>
          </Section>
        )}
        {more && list && (
          <Sheet title={t("suggest.title")} onClose={() => setMore(false)}>
            {[
              { title: t("suggest.due"), items: list.due },
              { title: t("suggest.usual"), items: list.usual.filter((one) => !due.has(one.id)) },
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
                        subtitle={habitDetail(t, product)}
                        action={{ icon: "plus", label: t("action.add_item", { name: product.name }), onClick: () => void add(product.name) }}
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
            title={t("empty.title")}
            action={{
              label: t("empty.action"),
              icon: "plus",
              onClick: () => document.querySelector<HTMLInputElement>(".text-field input")?.focus(),
            }}
          >
            {t("empty.body")}
          </EmptyState>
        )}

        {list?.groups.map((group) => (
          <Section key={group.category_id} title={`${group.emoji} ${sectionName(t, group.category_id, group.name)}`}>
            <List>
              {group.items.map((item) => (
                <SwipeRow
                  key={item.id}
                  label={item.name}
                  actions={[{ label: t("item.remove"), icon: "trash", tone: "danger", onAction: () => remove(item) }]}
                >
                  <CheckRow
                    title={item.name}
                    detail={itemDetail(item)}
                    checked={false}
                    onToggle={() => change((now) => withCart(now, item.id, true), () => setInCart(item, true))}
                    more={{ label: t("item.change", { name: item.name }), onClick: () => setOpen(item) }}
                  />
                </SwipeRow>
              ))}
            </List>
          </Section>
        ))}

        {list && list.cart.length > 0 && (
          <Section title={t("cart.title")} count={list.in_cart}>
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
            title={list.in_cart === 1 ? t("cart.one") : t("cart.other", { count: list.in_cart })}
            detail={cartLine(
              t,
              list.cart.map((item) => item.name),
            )}
            action={{ label: t("cart.finish"), icon: "done", onClick: () => setFinishing(true) }}
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
              setNotice(queued ? t("finish.queued") : t("finish.saved"));
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

export function noticeFor(t: Translate, added: Added[], categories: Category[]): string {
  const other = added.filter((one) => one.guessed && one.category_id === "other");
  if (other.length) {
    const section = sectionName(t, "other", categories.find((one) => one.id === "other")?.name);
    return t("notice.other", { names: other.map((one) => one.name).join(", "), section });
  }
  const already = added.filter((one) => one.already_on_list);
  if (already.length) return t("notice.already", { names: already.map((one) => one.name).join(", ") });
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
  const t = useT();

  async function run(action: () => Promise<ShoppingList>, offline: (now: ShoppingList) => ShoppingList) {
    setBusy(true);
    setProblem("");
    try {
      onSaved(await action());
    } catch (error) {
      if (error instanceof Queued) return onSaved((now) => (now ? offline(now) : (now as never)));
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("common.save_failed"));
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
        label: busy ? t("common.saving") : t("common.save"),
        onClick: () =>
          void run(save, (now) =>
            withSection(withEdited(now, item.id, quantity.trim() || null, note.trim() || null), item.id, category, categories),
          ),
        disabled: busy,
      }}
    >
      <TextField
        label={t("item.quantity")}
        value={quantity}
        onChange={setQuantity}
        placeholder={t("item.quantity_placeholder")}
      />
      <TextField label={t("item.note")} value={note} onChange={setNote} placeholder={t("item.note_placeholder")} />
      {provisional ? (
        <Hint>{t("item.provisional")}</Hint>
      ) : (
        <ChoiceChips
          label={t("item.section")}
          value={category}
          onChange={setCategoryId}
          options={categories.map((one) => ({ value: one.id, label: `${one.emoji} ${sectionName(t, one.id, one.name)}` }))}
        />
      )}
      {item.source === "tool" && <Hint>{t("item.by_claude")}</Hint>}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Button block disabled={busy} onClick={() => void run(() => dropItem(item), (now) => without(now, item.id))}>
        {t("item.remove_from_list")}
      </Button>
      <Hint>{t("item.remove_hint")}</Hint>
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
  const t = useT();

  async function finish() {
    setBusy(true);
    setProblem("");
    try {
      onFinished((await finishTrip()).list, false);
    } catch (error) {
      if (error instanceof Queued) return onFinished(withFinished(list), true);
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : t("finish.failed"));
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={t("finish.title")}
      onClose={onClose}
      action={{ label: busy ? t("common.saving") : t("finish.title"), onClick: () => void finish(), disabled: busy }}
    >
      <GroupLabel>{t("finish.taking", { count })}</GroupLabel>
      <List>
        {list.cart.map((item) => (
          <ListRow key={item.id} title={item.name} detail={itemDetail(item)} accessory="done" />
        ))}
      </List>
      {list.pending > 0 && (
        <>
          <GroupLabel>{t("finish.staying", { count: list.pending })}</GroupLabel>
          <List>
            {list.groups.flatMap((group) => group.items).map((item) => (
              <ListRow key={item.id} title={item.name} detail={itemDetail(item)} />
            ))}
          </List>
        </>
      )}
      <Hint>{count === 1 ? t("finish.hint_one") : t("finish.hint_other", { count })}</Hint>
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
    </Sheet>
  );
}
