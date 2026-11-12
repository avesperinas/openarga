import { Button, GroupLabel, Hint, SelectField, Sheet, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Traveller, type Trip, Unauthorised, readTravellers, signIn, updateTraveller } from "./api";
import { type Members, travellerLabel } from "./people";

export function TravellersSection({
  trip,
  members,
  onChanged,
}: {
  trip: Trip;
  members: Members;
  onChanged: () => void;
}) {
  const [people, setPeople] = useState<Traveller[] | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    readTravellers(trip.id)
      .then(setPeople)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setPeople([]);
      });
  }, [trip.id, trip.travellers, trip.companions.join("|")]);

  if (!people || people.length < 2) return null;
  return (
    <section className="travel-group">
      <GroupLabel>Viajeros</GroupLabel>
      <div className="surface travel-travellers">
        <p className="travel-travellers-names">{people.map((one) => travellerLabel(one, members)).join(" · ")}</p>
        <Button variant="plain" size="small" icon="edit" onClick={() => setEditing(true)}>
          Cambiar
        </Button>
      </div>
      {editing && (
        <TravellersSheet
          trip={trip}
          people={people}
          members={members}
          onClose={() => setEditing(false)}
          onSaved={(next) => {
            setPeople(next);
            setEditing(false);
            onChanged();
          }}
        />
      )}
    </section>
  );
}

const NOBODY = "";

function TravellersSheet({
  trip,
  people,
  members,
  onClose,
  onSaved,
}: {
  trip: Trip;
  people: Traveller[];
  members: Members;
  onClose: () => void;
  onSaved: (people: Traveller[]) => void;
}) {
  const [names, setNames] = useState(() => Object.fromEntries(people.map((one) => [one.id, one.name])));
  const [who, setWho] = useState(() => Object.fromEntries(people.map((one) => [one.id, one.member_user_id ?? NOBODY])));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const shared = Boolean(trip.space_id) && members.size > 0;

  const save = async () => {
    setBusy(true);
    let latest: Traveller[] = people;
    try {
      for (const one of people) {
        const change: { name?: string; member_user_id?: string | null } = {};
        const name = (names[one.id] ?? "").trim();
        if (name && name !== one.name) change.name = name;
        const member = who[one.id] || null;
        if (shared && member !== (one.member_user_id ?? null)) change.member_user_id = member;
        if (Object.keys(change).length) latest = await updateTraveller(trip.id, one.id, change);
      }
      onSaved(latest);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
    } finally {
      setBusy(false);
    }
  };

  const options = [
    { value: NOBODY, label: "Nadie de arga" },
    ...[...members.entries()].map(([value, label]) => ({ value, label })),
  ];
  return (
    <Sheet title="Viajeros" onClose={onClose} action={{ label: "Guardar", disabled: busy, onClick: () => void save() }}>
      <div className="travel-sheet-stack">
        {people.map((one) => (
          <div key={one.id} className="travel-traveller-edit">
            <TextField
              label={one.me ? "Tú" : `Viajero ${one.position + 1}`}
              value={names[one.id] ?? ""}
              onChange={(next) => setNames({ ...names, [one.id]: next })}
            />
            {shared && (
              <SelectField
                label="Es"
                value={who[one.id] ?? NOBODY}
                onChange={(next) => setWho({ ...who, [one.id]: next })}
                options={options}
              />
            )}
          </div>
        ))}
        {!shared && <Hint>Comparte el viaje con un espacio para decir quién es cada uno en arga.</Hint>}
        {problem && <Hint tone="warning">{problem}</Hint>}
      </div>
    </Sheet>
  );
}
