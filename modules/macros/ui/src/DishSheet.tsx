import { Button, ConfirmDelete, Hint, Inline, List, ListRow, Notice, Sheet, TextField, type Toast } from "@openarga/ui";
import { useState } from "react";

import { type Entry, type Item, dishToRecipe, removeItem, renameDish } from "./api";
import { amount, quantityLabel } from "./words";

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
  const items = entry.items.filter((item) => item.dish === dish);
  const [name, setName] = useState(dish);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const loose = items.filter((item) => item.kind !== "food").length;
  const kcal = items.reduce((sum, item) => sum + (item.nutrients.kcal ?? 0), 0);
  const fail = (reason: unknown) => {
    setBusy(false);
    setError(reason instanceof Error ? reason.message : "No se ha podido guardar");
  };

  const rename = () => {
    const next = name.trim();
    if (!next || next === dish) return onClose();
    setBusy(true);
    renameDish(entry.id, dish, next)
      .then(() => onChanged({ message: `Ahora se llama «${next}»` }))
      .catch(fail);
  };
  const split = () => {
    setBusy(true);
    renameDish(entry.id, dish, null)
      .then(() => onChanged({ message: `«${dish}», en sus cosas sueltas` }))
      .catch(fail);
  };
  const save = () => {
    setBusy(true);
    dishToRecipe(entry.id, dish)
      .then((found) =>
        onChanged({
          message: "Guardada en Recipes",
          action: { label: "Abrir", run: () => window.location.assign(`/recipes/receta/${found.recipe_id}`) },
        }),
      )
      .catch(fail);
  };

  return (
    <Sheet title={dish} onClose={onClose} action={{ label: "Guardar", onClick: rename, disabled: busy || !name.trim() }}>
      {error && <Notice tone="warning">{error}</Notice>}
      <TextField label="Nombre del plato" value={name} onChange={setName} onSubmit={rename} />
      <Hint>
        {items.length} {items.length === 1 ? "cosa" : "cosas"} · {amount(kcal, 0)} kcal
      </Hint>
      <List>
        {items.map((item) => (
          <ListRow
            key={item.id}
            title={item.name}
            subtitle={quantityLabel(item)}
            value={`${amount(item.nutrients.kcal ?? 0, 0)} kcal`}
            accessory="chevron-right"
            onClick={() => onItem(item)}
          />
        ))}
      </List>
      {loose > 0 && <Hint>Lo apuntado a ojo no pasa a la receta.</Hint>}
      <Inline label="Qué hacer con el plato">
        <Button variant="tinted" icon="book" disabled={busy} onClick={save}>
          Guardar como receta
        </Button>
        <Button variant="plain" disabled={busy} onClick={split}>
          Separar
        </Button>
        <Button variant="destructive" icon="trash" disabled={busy} onClick={() => setDeleting(true)}>
          Borrar el plato
        </Button>
      </Inline>
      {deleting && (
        <ConfirmDelete
          title="¿Borrar el plato?"
          subject={dish}
          consequence={`Se borran sus ${items.length} cosas de lo apuntado.`}
          action="Borrar el plato"
          onCancel={() => setDeleting(false)}
          onConfirm={() =>
            items
              .reduce<Promise<unknown>>((done, item) => done.then(() => removeItem(item.id)), Promise.resolve())
              .then(() => onChanged({ message: `Borrado · ${dish}` }))
          }
        />
      )}
    </Sheet>
  );
}
