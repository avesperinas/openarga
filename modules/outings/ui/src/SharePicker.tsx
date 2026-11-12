import { Hint, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import type { Space, Wish } from "./api";
import { t } from "./lang";

export function withWhom(space: Space): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return t("share.only_you_so_far");
  const names = [t("share.you"), ...others.map((member) => member.name ?? t("share.no_name"))];
  return t("share.and", { first: names.slice(0, -1).join(", "), last: names[names.length - 1]! });
}

export function sharedTitle(wish: Pick<Wish, "space_id">, spaces: Space[]): string {
  if (wish.space_id === null) return t("share.only_yours");
  return spaces.find((space) => space.id === wish.space_id)?.name ?? t("wish.shared");
}

export function sharedSubtitle(wish: Pick<Wish, "space_id" | "mine">, spaces: Space[]): string {
  if (wish.space_id === null) return t("share.only_you_see");
  const space = spaces.find((one) => one.id === wish.space_id);
  const who = space ? t("share.who", { who: withWhom(space) }) : t("share.in_space");
  return wish.mine ? who : t("share.shared_with_you", { who });
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
        <Sheet title={t("share.title")} onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="shield"
              title={t("share.only_yours")}
              subtitle={t("share.only_you_see")}
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
            <Hint>{t("share.unshare_hint")}</Hint>
          )}
          {spaces.length === 0 ? (
            <Hint>
              {t("share.create_before")} <a href="/">{t("share.settings_link")}</a> {t("share.create_after")}
            </Hint>
          ) : (
            <Hint>
              {t("share.change_before")} <a href="/">{t("share.settings_link")}</a>.
            </Hint>
          )}
        </Sheet>
      )}
    </>
  );
}
