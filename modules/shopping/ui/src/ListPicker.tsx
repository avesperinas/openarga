import { Button, Hint, Inline, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import type { ShoppingList, Space } from "./api";

export function withWhom(space: Space): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return "Solo tú, de momento";
  const names = ["Tú", ...others.map((member) => member.name ?? "Sin nombre")];
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`;
}

export function listTitle(list: Pick<ShoppingList, "space_id">, spaces: Space[]): string {
  if (list.space_id === null) return "Tu lista";
  return spaces.find((space) => space.id === list.space_id)?.name ?? "Lista compartida";
}

export function listSubtitle(list: Pick<ShoppingList, "space_id">, spaces: Space[]): string {
  const space = spaces.find((one) => one.id === list.space_id);
  return space ? `La ven y la marcan: ${withWhom(space)}` : "Solo la ves tú";
}

export function listLine(list: Pick<ShoppingList, "space_id">, spaces: Space[]): string {
  const space = spaces.find((one) => one.id === list.space_id);
  return space ? `${space.name} · ${withWhom(space)}` : listTitle(list, spaces);
}

export function ListPicker({
  list,
  spaces,
  onChoose,
}: {
  list: Pick<ShoppingList, "space_id">;
  spaces: Space[];
  onChoose: (spaceId: string | null) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function choose(spaceId: string | null) {
    setBusy(true);
    try {
      await onChoose(spaceId);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Inline>
        <Button
          size="small"
          icon={list.space_id ? "people" : "basket"}
          aria-label={`${listTitle(list, spaces)}. ${listSubtitle(list, spaces)}. Cambiar de lista`}
          onClick={() => setOpen(true)}
        >
          {listLine(list, spaces)}
        </Button>
      </Inline>
      {open && (
        <Sheet title="Qué lista usas" onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="basket"
              title="Tu lista"
              subtitle="Solo la ves tú"
              accessory={list.space_id === null ? "done" : undefined}
              disabled={busy}
              onClick={() => void choose(null)}
            />
            {spaces.map((space) => (
              <ListRow
                key={space.id}
                icon="people"
                title={space.name}
                subtitle={withWhom(space)}
                accessory={list.space_id === space.id ? "done" : undefined}
                disabled={busy}
                onClick={() => void choose(space.id)}
              />
            ))}
          </List>
          <Hint>
            La app, los widgets y Claude usan la que elijas. Cambiar no mueve nada: tu lista sigue
            aquí para cuando vuelvas.
          </Hint>
          {spaces.length === 0 ? (
            <Hint>
              Para compartirla, crea un espacio en los <a href="/">Ajustes de arga</a> e invita a
              quien haga la compra contigo.
            </Hint>
          ) : (
            <Hint>
              Los espacios y quién está en ellos se cambian en los <a href="/">Ajustes de arga</a>.
            </Hint>
          )}
        </Sheet>
      )}
    </>
  );
}
