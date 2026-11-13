import { Button, ConfirmDelete, Hint, Inline, List, ListRow, Notice, Sheet, TextField, type Toast, useLocale, useT } from "@openarga/ui";
import { useState } from "react";

import { type Entry, type Item, dishToRecipe, removeItem, renameDish } from "./api";
import { amount, plural, quantityLabel } from "./words";

export function DishSheet({
  entry,
  dish,
  onItem,
  onClose,
  onChanged,
}: {
  entry: Entry;
  dish: string;
  onItem: (item: Item) => void;
  onClose: () => void;
  onChanged: (toast?: Toast) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const items = entry.items.filter((item) => item.dish === dish);
  const [name, setName] = useState(dish);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const loose = items.filter((item) => item.kind !== "food").length;
  const kcal = items.reduce((sum, item) => sum + (item.nutrients.kcal ?? 0), 0);
  const fail = (reason: unknown) => {
    setBusy(false);
    setError(reason instanceof Error ? reason.message : t("common.save_failed"));
  };

  const rename = () => {
    const next = name.trim();
    if (!next || next === dish) return onClose();
    setBusy(true);
    renameDish(entry.id, dish, next)
      .then(() => onChanged({ message: t("dish.renamed", { name: next }) }))
      .catch(fail);
  };
  const split = () => {
    setBusy(true);
    renameDish(entry.id, dish, null)
      .then(() => onChanged({ message: t("dish.split_done", { name: dish }) }))
      .catch(fail);
  };
  const save = () => {
    setBusy(true);
    dishToRecipe(entry.id, dish)
      .then((found) =>
        onChanged({
          message: t("dish.saved_recipe"),
          action: { label: t("common.open"), run: () => window.location.assign(`/recipes/receta/${found.recipe_id}`) },
        }),
      )
      .catch(fail);
  };

  return (
    <Sheet title={dish} onClose={onClose} action={{ label: t("common.save"), onClick: rename, disabled: busy || !name.trim() }}>
      {error && <Notice tone="warning">{error}</Notice>}
      <TextField label={t("dish.name")} value={name} onChange={setName} onSubmit={rename} />
      <Hint>
        {plural(t, "things", items.length)} · {amount(kcal, 0)} kcal
      </Hint>
      <List>
        {items.map((item) => (
          <ListRow
            key={item.id}
            title={item.name}
            subtitle={quantityLabel(item, t, locale)}
            value={`${amount(item.nutrients.kcal ?? 0, 0)} kcal`}
            accessory="chevron-right"
            onClick={() => onItem(item)}
          />
        ))}
      </List>
      {loose > 0 && <Hint>{t("dish.loose")}</Hint>}
      <Inline label={t("dish.actions")}>
        <Button variant="tinted" icon="book" disabled={busy} onClick={save}>
          {t("dish.save_recipe")}
        </Button>
        <Button variant="plain" disabled={busy} onClick={split}>
          {t("dish.split")}
        </Button>
        <Button variant="destructive" icon="trash" disabled={busy} onClick={() => setDeleting(true)}>
          {t("dish.delete")}
        </Button>
      </Inline>
      {deleting && (
        <ConfirmDelete
          title={t("dish.delete_title")}
          subject={dish}
          consequence={t("dish.delete_consequence", { count: items.length })}
          action={t("dish.delete")}
          onCancel={() => setDeleting(false)}
          onConfirm={() =>
            items
              .reduce<Promise<unknown>>((done, item) => done.then(() => removeItem(item.id)), Promise.resolve())
              .then(() => onChanged({ message: t("common.deleted", { name: dish }) }))
          }
        />
      )}
    </Sheet>
  );
}
