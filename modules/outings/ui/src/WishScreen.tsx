import { Button, Card, ConfirmDelete, Hint, List, ListRow, OfflineNotice, Photo, Screen } from "@openarga/ui";
import { useCallback, useState } from "react";

import {
  Unauthorised,
  deleteWish,
  markDone,
  wishToIdea,
  creditLine,
  photoUrl,
  readSpaces,
  readWish,
  restoreWish,
  shareWish,
  signIn,
} from "./api";
import { ScreenHeader } from "./Header";
import { t } from "./lang";
import { Pending, changed, useLoad } from "./Loads";
import { MiniMap } from "./MiniMap";
import { SharePicker } from "./SharePicker";
import { WishSheet } from "./WishSheet";
import { doneLine, kindOf, placeLine, span } from "./words";

export function WishScreen({ id, onBack, onEvent }: { id: string; onBack: () => void; onEvent?: (id: string) => void }) {
  const { data: wish, set: setWish, found } = useLoad(`wish:${id}`, () => readWish(id));
  const spaces = useLoad("spaces", readSpaces).data ?? [];
  const [problem, setProblem] = useState("");
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : t("problem.save"));
  }, []);

  async function toggleDone() {
    if (!wish) return;
    setProblem("");
    try {
      setWish(wish.done_at ? await restoreWish(wish.id) : await markDone(wish.id));
    } catch (error) {
      fail(error);
    }
  }

  const back = { label: t("tab.wishes"), onClick: onBack };
  if (!wish) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <OfflineNotice />
        <Pending found={found} />
      </Screen>
    );
  }

  const kind = kindOf(wish.kind);
  const photo = photoUrl(wish);
  const where = wish.place ? placeLine(wish.place) : undefined;

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={kind.label} title={wish.name} />

      <OfflineNotice />

      <Photo src={photo} alt={wish.name} hue={kind.hue} icon={kind.icon} shape="hero" loading="eager" />
      {photo && wish.photo_credit && (
        <a className="outings-credit" href={wish.photo_credit.page} target="_blank" rel="noreferrer">
          {creditLine(wish.photo_credit)}
        </a>
      )}

      {wish.done_at && <Hint>{doneLine(wish)}</Hint>}
      {problem && <Hint tone="warning">{problem}</Hint>}

      {wish.body && <p className="outings-body">{wish.body}</p>}

      {wish.starts_on && (
        <List>
          <ListRow
            title={span({ starts_on: wish.starts_on, ends_on: wish.ends_on ?? wish.starts_on })}
            subtitle={wish.event_id ? t("wish.from_agenda") : undefined}
            icon="calendar"
            hue={kind.hue}
            accessory={wish.event_id && wish.mine && onEvent ? "chevron-right" : undefined}
            onClick={wish.event_id && wish.mine && onEvent ? () => onEvent(wish.event_id!) : undefined}
          />
        </List>
      )}

      {wish.place && (
        <Card flush>
          {wish.place.lat != null && wish.place.lon != null && (
            <MiniMap point={{ id: wish.id, lon: wish.place.lon, lat: wish.place.lat, kind: "photo", image: photoUrl(wish, "thumb"), icon: kind.icon, hue: kind.hue, title: wish.name }} label={t("wish.where", { place: wish.place.name })} />
          )}
        <List>
          <ListRow
            title={wish.place.name}
            subtitle={where === wish.place.name ? undefined : where}
            detail={wish.place.lat == null ? t("place.unplaced") : undefined}
            icon="pin"
            hue={kind.hue}
          />
        </List>
        </Card>
      )}

      <SharePicker
        wish={wish}
        spaces={spaces}
        onChoose={async (spaceId) => {
          try {
            setWish(await shareWish(wish.id, spaceId));
          } catch (error) {
            fail(error);
          }
        }}
      />

      <div className="outings-actions">
        <Button variant="tinted" icon={wish.done_at ? "undo" : "done"} onClick={() => void toggleDone()}>
          {wish.done_at ? t("wishes.restore") : t("wishes.done")}
        </Button>
        <Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>
          {t("action.edit")}
        </Button>
        {wish.kind === "trip" && !wish.done_at && (
          <Button
            variant="secondary"
            icon="plane"
            onClick={async () => {
              try {
                const idea = await wishToIdea(wish.id);
                window.location.assign(idea.href);
              } catch (error) {
                fail(error);
              }
            }}
          >
            {t("wish.to_idea")}
          </Button>
        )}
        {wish.mine && (
          <Button variant="plain" icon="trash" onClick={() => setDeleting(true)}>
            {t("action.delete")}
          </Button>
        )}
      </div>

      {editing && (
        <WishSheet
          wish={wish}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            setProblem("");
            setWish(saved);
          }}
          onError={fail}
        />
      )}
      {deleting && (
        <ConfirmDelete
          title={t("wish.delete_title")}
          subject={wish.name}
          consequence={t("wish.delete_consequence")}
          action={t("wish.delete_action")}
          onCancel={() => setDeleting(false)}
          onConfirm={async () => {
            await deleteWish(wish.id);
            changed();
            onBack();
          }}
        />
      )}
    </Screen>
  );
}
