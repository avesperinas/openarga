import { Hint, List, ListRow, Sheet } from "@openarga/ui";
import { useState } from "react";

import type { Space, Trip } from "./api";

export function withWhom(space: Space): string {
  const others = space.members.filter((member) => member.user_id !== space.me);
  if (others.length === 0) return "Solo tú, de momento";
  const names = ["Tú", ...others.map((member) => member.name ?? "Sin nombre")];
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`;
}

export function sharedTitle(trip: Pick<Trip, "space_id">, spaces: Space[]): string {
  if (trip.space_id === null) return "Solo tuyo";
  return spaces.find((space) => space.id === trip.space_id)?.name ?? "Compartido";
}

export function sharedSubtitle(trip: Pick<Trip, "space_id" | "mine">, spaces: Space[]): string {
  if (trip.space_id === null) return "Solo lo ves tú";
  const space = spaces.find((one) => one.id === trip.space_id);
  const who = space ? `Lo ven y lo editan: ${withWhom(space)}` : "Compartido en un espacio";
  return trip.mine ? who : `${who}. Te lo compartieron`;
}

export function SharePicker({
  trip,
  spaces,
  onChoose,
}: {
  trip: Pick<Trip, "space_id" | "mine">;
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
          icon={trip.space_id ? "people" : "shield"}
          title={sharedTitle(trip, spaces)}
          subtitle={sharedSubtitle(trip, spaces)}
          accessory={trip.mine ? "chevron-right" : undefined}
          onClick={trip.mine ? () => setOpen(true) : undefined}
        />
      </List>
      {open && (
        <Sheet title="Con quién lo compartes" onClose={() => setOpen(false)}>
          <List>
            <ListRow
              icon="shield"
              title="Solo tuyo"
              subtitle="Solo lo ves tú"
              accessory={trip.space_id === null ? "done" : undefined}
              disabled={busy}
              onClick={() => void choose(null)}
            />
            {spaces.map((space) => (
              <ListRow
                key={space.id}
                icon="people"
                title={space.name}
                subtitle={withWhom(space)}
                accessory={trip.space_id === space.id ? "done" : undefined}
                disabled={busy}
                onClick={() => void choose(space.id)}
              />
            ))}
          </List>
          {trip.space_id !== null && (
            <Hint>
              Si dejas de compartirlo, todo lo que apuntaron los demás se queda en tu viaje, y ellos
              dejan de verlo.
            </Hint>
          )}
          {spaces.length === 0 ? (
            <Hint>
              Para compartirlo, crea un espacio en los <a href="/">Ajustes de arga</a> e invita a
              quien viajó contigo.
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
