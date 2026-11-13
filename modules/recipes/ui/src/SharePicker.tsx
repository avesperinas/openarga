import { Button, Hint, List, ListRow, Sheet, type Translate, useT } from "@openarga/ui";
import { useState } from "react";

import type { Recipe, Space } from "./api";

export function withWhom(space: Space, t: Translate): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return t("share.only_you_now");
  const names = [t("share.you"), ...others.map((member) => member.name ?? t("share.no_name"))];
  return `${names.slice(0, -1).join(", ")}${t("common.and")}${names[names.length - 1]}`;
}

export function sharedTitle(recipe: Pick<Recipe, "space_id">, spaces: Space[], t: Translate): string {
  if (recipe.space_id === null) return t("share.only_yours");
  return spaces.find((space) => space.id === recipe.space_id)?.name ?? t("share.shared");
}

export function sharedSubtitle(recipe: Pick<Recipe, "space_id" | "mine">, spaces: Space[], t: Translate): string {
  if (recipe.space_id === null) return t("share.only_you_see");
  const space = spaces.find((one) => one.id === recipe.space_id);
  const who = space ? t("share.who", { names: withWhom(space, t) }) : t("share.in_a_space");
  return recipe.mine ? who : t("share.from_someone", { who });
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
  const t = useT();
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
        aria-label={`${sharedTitle(recipe, spaces, t)}. ${sharedSubtitle(recipe, spaces, t)}${recipe.mine ? `. ${t("share.change")}` : ""}`}
        disabled={!recipe.mine}
        onClick={() => setOpen(true)}
      >
        {sharedTitle(recipe, spaces, t)}
      </Button>
      {open && (
        <Sheet title={t("share.title")} onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="shield"
              title={t("share.only_yours")}
              subtitle={t("share.only_you_see")}
              accessory={recipe.space_id === null ? "done" : undefined}
              disabled={busy}
              onClick={() => void choose(null)}
            />
            {spaces.map((space) => (
              <ListRow
                key={space.id}
                icon="people"
                title={space.name}
                subtitle={withWhom(space, t)}
                accessory={recipe.space_id === space.id ? "done" : undefined}
                disabled={busy}
                onClick={() => void choose(space.id)}
              />
            ))}
          </List>
          {recipe.space_id !== null && (
            <Hint>{t("share.unshare_hint")}</Hint>
          )}
          {spaces.length === 0 ? (
            <Hint>
              {t("share.create_before")} <a href="/">{t("share.settings")}</a> {t("share.create_after")}
            </Hint>
          ) : (
            <Hint>
              {t("share.change_before")} <a href="/">{t("share.settings")}</a>.
            </Hint>
          )}
        </Sheet>
      )}
    </>
  );
}
