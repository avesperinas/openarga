import {
  Button,
  CANNOT_UNDO,
  ConfirmDelete,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Sheet,
  TextField,
} from "@openarga/ui";
import { useState } from "react";

import { type OtherPlace, type Place, addOtherPlace, deleteOtherPlace } from "./api";
import { PlacePicker } from "./PlacePicker";
import { flag } from "./words";

const where = (place: Place) => [place.region, place.country].filter(Boolean).join(", ") || "Sin situar";

export function OtherPlaces({ others, onChanged }: { others: OtherPlace[]; onChanged: () => void }) {
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<OtherPlace | null>(null);

  return (
    <section className="travel-group">
      <GroupLabel>
        Otros lugares
        <span className="travel-group-detail">sin viaje apuntado</span>
      </GroupLabel>
      {others.length === 0 ? (
        <Hint>
          Escapadas pequeñas o viajes tan antiguos que no recuerdas las fechas. Salen en el mapa y
          cuentan en países y regiones, no en viajes ni noches.
        </Hint>
      ) : (
        <List>
          {others.map((one) => (
            <ListRow
              key={one.id}
              title={`${flag(one.place.country_code)} ${one.place.name}`}
              subtitle={[where(one.place), one.note].filter(Boolean).join(" · ")}
              accessory="trash"
              aria-label={`Quitar ${one.place.name}`}
              onClick={() => setRemoving(one)}
            />
          ))}
        </List>
      )}
      <Button variant="secondary" icon="plus" onClick={() => setAdding(true)}>
        Añadir lugar
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
          title="¿Quitar este lugar?"
          subject={`${removing.place.name} · ${where(removing.place)}`}
          consequence={`Deja de contar en el mapa si no has estado allí en ningún viaje. ${CANNOT_UNDO}`}
          action="Quitar lugar"
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
      setFailed(error instanceof Error ? error.message : "No se ha podido añadir el lugar.");
    }
  };

  return (
    <Sheet title="Añadir lugar" onClose={onClose}>
      <div className="travel-sheet-stack">
        <TextField
          label="Nota"
          value={note}
          onChange={setNote}
          placeholder="Con quién, hacia qué año…"
          hint="Opcional. Escríbela antes de elegir el lugar."
        />
        <PlacePicker label="Lugar" onPick={(place) => void add(place)} />
        {failed && (
          <Hint tone="warning">
            {failed}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}
