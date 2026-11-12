import { Button, Hint, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import type { Recipe, Space } from "./api";

export function withWhom(space: Space): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return "Solo tú, de momento";
  const names = ["Tú", ...others.map((member) => member.name ?? "Sin nombre")];
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`;
}

export function sharedTitle(recipe: Pick<Recipe, "space_id">, spaces: Space[]): string {
  if (recipe.space_id === null) return "Solo tuya";
  return spaces.find((space) => space.id === recipe.space_id)?.name ?? "Compartida";
}

export function sharedSubtitle(recipe: Pick<Recipe, "space_id" | "mine">, spaces: Space[]): string {
  if (recipe.space_id === null) return "Solo la ves tú";
  const space = spaces.find((one) => one.id === recipe.space_id);
  const who = space ? `La ven y la cocinan: ${withWhom(space)}` : "Compartido en un espacio";
  return recipe.mine ? who : `${who}. Te la compartieron`;
}

export function SharePicker({
  recipe,
  spaces,
  onChoose,
}: {
  recipe: Pick<Recipe, "space_id" | "mine">;
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
      <Button
        icon={recipe.space_id ? "people" : "shield"}
        aria-label={`${sharedTitle(recipe, spaces)}. ${sharedSubtitle(recipe, spaces)}${recipe.mine ? ". Cambiar con quién la compartes" : ""}`}
        disabled={!recipe.mine}
        onClick={() => setOpen(true)}
      >
        {sharedTitle(recipe, spaces)}
      </Button>
      {open && (
        <Sheet title="Con quién la compartes" onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="shield"
              title="Solo tuya"
              subtitle="Solo la ves tú"
              accessory={recipe.space_id === null ? "done" : undefined}
              disabled={busy}
              onClick={() => void choose(null)}
            />
            {spaces.map((space) => (
              <ListRow
                key={space.id}
                icon="people"
                title={space.name}
                subtitle={withWhom(space)}
                accessory={recipe.space_id === space.id ? "done" : undefined}
                disabled={busy}
                onClick={() => void choose(space.id)}
              />
            ))}
          </List>
          {recipe.space_id !== null && (
            <Hint>
              Si dejas de compartirla, las versiones que escribieron los demás se quedan en tu receta, y ellos
              dejan de verla.
            </Hint>
          )}
          {spaces.length === 0 ? (
            <Hint>
              Para compartirla, crea un espacio en los <a href="/">Ajustes de arga</a> e invita a
              quien cocina contigo.
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
