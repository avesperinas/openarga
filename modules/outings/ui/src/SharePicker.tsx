import { Hint, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import type { Space, Wish } from "./api";

export function withWhom(space: Space): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return "Solo tú, de momento";
  const names = ["Tú", ...others.map((member) => member.name ?? "Sin nombre")];
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`;
}

export function sharedTitle(wish: Pick<Wish, "space_id">, spaces: Space[]): string {
  if (wish.space_id === null) return "Solo tuya";
  return spaces.find((space) => space.id === wish.space_id)?.name ?? "Compartida";
}

export function sharedSubtitle(wish: Pick<Wish, "space_id" | "mine">, spaces: Space[]): string {
  if (wish.space_id === null) return "Solo la ves tú";
  const space = spaces.find((one) => one.id === wish.space_id);
  const who = space ? `La ven y la editan: ${withWhom(space)}` : "Compartido en un espacio";
  return wish.mine ? who : `${who}. Te la compartieron`;
}

export function SharePicker({
  wish,
  spaces,
  onChoose,
}: {
  wish: Pick<Wish, "space_id" | "mine">;
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
      <List>
        <ListRow
          icon={wish.space_id ? "people" : "shield"}
          title={sharedTitle(wish, spaces)}
          subtitle={sharedSubtitle(wish, spaces)}
          accessory={wish.mine ? "chevron-right" : undefined}
          onClick={wish.mine ? () => setOpen(true) : undefined}
        />
      </List>
      {open && (
        <Sheet title="Con quién la compartes" onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="shield"
              title="Solo tuya"
              subtitle="Solo la ves tú"
              accessory={wish.space_id === null ? "done" : undefined}
              disabled={busy}
              onClick={() => void choose(null)}
            />
            {spaces.map((space) => (
              <ListRow
                key={space.id}
                icon="people"
                title={space.name}
                subtitle={withWhom(space)}
                accessory={wish.space_id === space.id ? "done" : undefined}
                disabled={busy}
                onClick={() => void choose(space.id)}
              />
            ))}
          </List>
          {wish.space_id !== null && (
            <Hint>
              Si dejas de compartirla, la foto que pusieron los demás se queda en tu gana, y ellos
              dejan de verla.
            </Hint>
          )}
          {spaces.length === 0 ? (
            <Hint>
              Para compartirla, crea un espacio en los <a href="/">Ajustes de arga</a> e invita a
              con quien haces planes.
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
