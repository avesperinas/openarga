import { Button, Hint, Inline, List, ListRow, Sheet, type Translate, useT } from "@openarga/ui";
import { useState } from "react";

import type { ShoppingList, Space } from "./api";

export function withWhom(t: Translate, space: Space): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return t("picker.whom_alone");
  const names = [t("picker.whom_you"), ...others.map((member) => member.name ?? t("picker.whom_nameless"))];
  return t("picker.whom_and", { first: names.slice(0, -1).join(", "), last: names[names.length - 1]! });
}

export function listTitle(t: Translate, list: Pick<ShoppingList, "space_id">, spaces: Space[]): string {
  if (list.space_id === null) return t("picker.yours");
  return spaces.find((space) => space.id === list.space_id)?.name ?? t("picker.shared");
}

export function listSubtitle(t: Translate, list: Pick<ShoppingList, "space_id">, spaces: Space[]): string {
  const space = spaces.find((one) => one.id === list.space_id);
  return space ? t("picker.whom_see", { whom: withWhom(t, space) }) : t("picker.only_you");
}

export function listLine(t: Translate, list: Pick<ShoppingList, "space_id">, spaces: Space[]): string {
  const space = spaces.find((one) => one.id === list.space_id);
  return space ? `${space.name} · ${withWhom(t, space)}` : listTitle(t, list, spaces);
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
  const t = useT();
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
          aria-label={t("picker.change", { title: listTitle(t, list, spaces), subtitle: listSubtitle(t, list, spaces) })}
          onClick={() => setOpen(true)}
        >
          {listLine(t, list, spaces)}
        </Button>
      </Inline>
      {open && (
        <Sheet title={t("picker.title")} onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="basket"
              title={t("picker.yours")}
              subtitle={t("picker.only_you")}
              accessory={list.space_id === null ? "done" : undefined}
              disabled={busy}
              onClick={() => void choose(null)}
            />
            {spaces.map((space) => (
              <ListRow
                key={space.id}
                icon="people"
                title={space.name}
                subtitle={withWhom(t, space)}
                accessory={list.space_id === space.id ? "done" : undefined}
                disabled={busy}
                onClick={() => void choose(space.id)}
              />
            ))}
          </List>
          <Hint>{t("picker.hint")}</Hint>
          {spaces.length === 0 ? (
            <Hint>
              {t("picker.share_before")}
              <a href="/">{t("picker.settings")}</a>
              {t("picker.share_after")}
            </Hint>
          ) : (
            <Hint>
              {t("picker.spaces_before")}
              <a href="/">{t("picker.settings")}</a>
              {t("picker.spaces_after")}
            </Hint>
          )}
        </Sheet>
      )}
    </>
  );
}
