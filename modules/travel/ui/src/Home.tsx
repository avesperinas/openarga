import { Button, GroupLabel, Hint, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import { type Place, clearHome, setHome } from "./api";
import { PlacePicker } from "./PlacePicker";
import { flag } from "./words";

export function HomePlace({ home, onChanged }: { home: Place | null; onChanged: () => void }) {
  const [choosing, setChoosing] = useState(false);
  const [failed, setFailed] = useState("");

  const choose = async (place: Place) => {
    setFailed("");
    try {
      await setHome(place.id);
      setChoosing(false);
      onChanged();
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "No se ha podido guardar dónde vives.");
    }
  };

  const forget = async () => {
    setFailed("");
    try {
      await clearHome();
      setChoosing(false);
      onChanged();
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "No se ha podido quitar.");
    }
  };

  return (
    <section className="travel-group">
      <GroupLabel>
        Dónde vives
        <span className="travel-group-detail">de otro color en el mapa</span>
      </GroupLabel>
      {home ? (
        <List>
          <ListRow
            title={`${flag(home.country_code)} ${home.name}`}
            subtitle={[home.region, home.country].filter(Boolean).join(", ") || "Sin situar"}
            accessory="chevron-right"
            aria-label={`Cambiar dónde vives, ahora ${home.name}`}
            onClick={() => setChoosing(true)}
          />
        </List>
      ) : (
        <>
          <Hint>
            Tu país y tu región salen en el mapa de otro color. No cuentan como visitados.
          </Hint>
          <Button variant="secondary" icon="plus" onClick={() => setChoosing(true)}>
            Elegir dónde vives
          </Button>
        </>
      )}

      {choosing && (
        <Sheet title="Dónde vives" onClose={() => setChoosing(false)}>
          <div className="travel-sheet-stack">
            <PlacePicker label="Ciudad o pueblo" onPick={(place) => void choose(place)} />
            {home && (
              <Button variant="plain" onClick={() => void forget()}>
                No pintar dónde vivo
              </Button>
            )}
            {failed && (
              <Hint tone="warning">
                {failed}
              </Hint>
            )}
          </div>
        </Sheet>
      )}
    </section>
  );
}
