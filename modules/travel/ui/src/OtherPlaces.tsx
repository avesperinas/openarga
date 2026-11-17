import {
  Button,
  ConfirmDelete,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Sheet,
  TextField,
  cannotUndo,
} from "@openarga/ui";
import { useState } from "react";

import { type OtherPlace, type Place, addOtherPlace, deleteOtherPlace } from "./api";
import { PlacePicker } from "./PlacePicker";
import { flag } from "./words";
import { t } from "./lang";

const where = (place: Place) => [place.region, place.country].filter(Boolean).join(", ") || t("other.unplaced");

export function OtherPlaces({ others, onChanged }: { others: OtherPlace[]; onChanged: () => void }) {
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<OtherPlace | null>(null);

  return (
    <section className="travel-group">
      <GroupLabel>
        {t("other.title")}
        <span className="travel-group-detail">{t("other.detail")}</span>
      </GroupLabel>
      {others.length === 0 ? (
        <Hint>
          {t("other.hint")}
        </Hint>
      ) : (
        <List>
          {others.map((one) => (
            <ListRow
              key={one.id}
              title={`${flag(one.place.country_code)} ${one.place.name}`}
              subtitle={[where(one.place), one.note].filter(Boolean).join(" · ")}
              accessory="trash"
              aria-label={t("editor.remove", { what: one.place.name })}
              onClick={() => setRemoving(one)}
            />
          ))}
        </List>
      )}
      <Button variant="secondary" icon="plus" onClick={() => setAdding(true)}>
        {t("other.add")}
      </Button>

      {adding && (
        <AddSheet
          onClose={() => setAdding(false)}
          onAdded={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title={t("other.remove_confirm")}
          subject={`${removing.place.name} · ${where(removing.place)}`}
          consequence={`${t("other.remove_consequence")} ${cannotUndo()}`}
          action={t("other.remove")}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await deleteOtherPlace(removing.id);
            setRemoving(null);
            onChanged();
          }}
        />
      )}
    </section>
  );
}

function AddSheet({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [note, setNote] = useState("");
  const [failed, setFailed] = useState("");

  const add = async (place: Place) => {
    setFailed("");
    try {
      await addOtherPlace({ place_id: place.id, note: note.trim() || null });
      onAdded();
    } catch (error) {
      setFailed(error instanceof Error ? error.message : t("other.error.add"));
    }
  };

  return (
    <Sheet title={t("other.add")} onClose={onClose}>
      <div className="travel-sheet-stack">
        <TextField
          label={t("editor.note")}
          value={note}
          onChange={setNote}
          placeholder={t("other.note_example")}
          hint={t("other.note_hint")}
        />
        <PlacePicker label={t("atlas.place")} onPick={(place) => void add(place)} />
        {failed && (
          <Hint tone="warning">
            {failed}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}
