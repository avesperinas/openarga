import { Button, CheckRow, ChoiceChips, GroupLabel, Hint, SegmentedControl, SelectField, Sheet, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import {
  type CheckItem,
  type ListKind,
  type Traveller,
  type Trip,
  Unauthorised,
  addCheckItems,
  copyChecklist,
  readAtlas,
  readChecklist,
  changeCheckItem,
  readTravellers,
  removeCheckItem,
  setChecked,
  signIn,
} from "./api";
import { Queued } from "./offline";
import { type Members, travellerLabel } from "./people";

const LISTS: Record<ListKind, string> = { packing: "Maleta", todo: "Antes de irte" };

export function ChecklistSection({ trip, members, version }: { trip: Trip; members: Members; version: number }) {
  const [found, setFound] = useState<CheckItem[] | null>(null);
  const [people, setPeople] = useState<Traveller[]>([]);
  const [list, setList] = useState<ListKind>("packing");
  const [text, setText] = useState("");
  const [copying, setCopying] = useState(false);
  const [open, setOpen] = useState<CheckItem | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readChecklist(trip.id)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setFound([]);
      });
  }, [trip.id]);

  useEffect(() => {
    readTravellers(trip.id)
      .then(setPeople)
      .catch(() => setPeople([]));
  }, [trip.id, version]);
  const nameOf = (id: string | null | undefined) => {
    const one = id ? people.find((person) => person.id === id) : undefined;
    return one ? travellerLabel(one, members) : undefined;
  };

  const apply = async (change: Promise<CheckItem[]>, offline?: (now: CheckItem[]) => CheckItem[]) => {
    try {
      setFound(await change);
      setProblem("");
      return true;
    } catch (error) {
      if (error instanceof Queued) {
        if (offline) setFound((now) => offline(now ?? []));
        setProblem(error.message);
        return true;
      }
      setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
      return false;
    }
  };

  if (found === null) return null;
  const shown = found.filter((one) => one.list === list);
  const done = shown.filter((one) => one.checked).length;

  const add = async () => {
    const texts = text
      .split(/[\n;]/)
      .map((one) => one.trim())
      .filter(Boolean);
    if (texts.length === 0) return;
    const ok = await apply(addCheckItems(trip.id, list, texts), (now) => [
      ...now,
      ...texts.map((one, index) => ({ id: `nuevo-${index}-${one}`, list, text: one, position: now.length + index, checked: false })),
    ]);
    if (ok) setText("");
  };

  return (
    <section className="travel-group">
      <GroupLabel>Listas</GroupLabel>
      <SegmentedControl
        label="Lista"
        value={list}
        onChange={setList}
        options={(Object.keys(LISTS) as ListKind[]).map((value) => {
          const count = found.filter((one) => one.list === value);
          const left = count.filter((one) => !one.checked).length;
          return { value, label: count.length ? `${LISTS[value]} · ${left}` : LISTS[value] };
        })}
      />
      {problem && <Hint tone="warning">{problem}</Hint>}
      <div className="surface travel-checklist">
        {shown.length > 0 && (
          <p className="travel-checklist-count">
            {done === shown.length ? "Todo listo." : `${done} de ${shown.length}`}
          </p>
        )}
        {shown.map((item) => (
          <CheckRow
            key={item.id}
            title={item.text}
            detail={nameOf(item.traveller_id)}
            checked={item.checked}
            onToggle={() =>
              void apply(setChecked(trip.id, item, !item.checked), (now) =>
                now.map((one) => (one.id === item.id ? { ...one, checked: !item.checked } : one)),
              )
            }
            more={{ label: `Cambiar «${item.text}»`, onClick: () => setOpen(item) }}
          />
        ))}
        {shown.length === 0 && (
          <p className="travel-checklist-count">
            {list === "packing" ? "Pasaporte, cargador, adaptador…" : "Seguro, visado, reservar el coche…"}
          </p>
        )}
        <form
          className="travel-checklist-add"
          onSubmit={(event) => {
            event.preventDefault();
            void add();
          }}
        >
          <TextField label={list === "packing" ? "Meter en la maleta" : "Hacer antes de irte"} value={text} onChange={setText} />
          <Button type="submit" variant="tinted" icon="plus" disabled={!text.trim()}>
            Añadir
          </Button>
        </form>
      </div>
      <div className="travel-actions">
        <Button variant="plain" size="small" icon="copy" onClick={() => setCopying(true)}>
          Copiar de otro viaje
        </Button>
      </div>
      {open && (
        <ItemSheet
          item={open}
          people={people.map((one) => ({ value: one.id, label: travellerLabel(one, members) }))}
          onClose={() => setOpen(null)}
          onSave={async (change) => {
            const ok = await apply(changeCheckItem(trip.id, open, change), (now) =>
              now.map((one) => (one.id === open.id ? { ...one, ...change } : one)),
            );
            if (ok) setOpen(null);
          }}
          onRemove={async () => {
            const ok = await apply(removeCheckItem(trip.id, open.id), (now) => now.filter((one) => one.id !== open.id));
            if (ok) setOpen(null);
          }}
        />
      )}
      {copying && (
        <CopySheet
          trip={trip}
          list={list}
          onClose={() => setCopying(false)}
          onCopy={async (from) => {
            if (await apply(copyChecklist(trip.id, from, list))) setCopying(false);
          }}
        />
      )}
    </section>
  );
}

function ItemSheet({
  item,
  people,
  onClose,
  onSave,
  onRemove,
}: {
  item: CheckItem;
  people: { value: string; label: string }[];
  onClose: () => void;
  onSave: (change: { text?: string; traveller_id?: string | null }) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const [text, setText] = useState(item.text);
  const [owner, setOwner] = useState<string | null>(item.traveller_id ?? null);
  const [busy, setBusy] = useState(false);
  const change: { text?: string; traveller_id?: string | null } = {};
  if (text.trim() && text.trim() !== item.text) change.text = text.trim();
  if (owner !== (item.traveller_id ?? null)) change.traveller_id = owner;
  const run = (work: Promise<void>) => {
    setBusy(true);
    void work.finally(() => setBusy(false));
  };
  return (
    <Sheet
      title="Cambiar"
      onClose={onClose}
      action={{
        label: "Guardar",
        disabled: !text.trim() || Object.keys(change).length === 0 || busy,
        onClick: () => run(onSave(change)),
      }}
    >
      <div className="travel-sheet-stack">
        <TextField label="Qué" value={text} onChange={setText} autoFocus />
        {people.length > 1 && (
          <ChoiceChips
            label="Le toca a"
            value={owner}
            onChange={(next) => setOwner(next === owner ? null : next)}
            options={people}
          />
        )}
        <Button variant="plain" icon="trash" disabled={busy} onClick={() => run(onRemove())}>
          Quitar de la lista
        </Button>
      </div>
    </Sheet>
  );
}

function CopySheet({
  trip,
  list,
  onClose,
  onCopy,
}: {
  trip: Trip;
  list: ListKind;
  onClose: () => void;
  onCopy: (from: string) => Promise<void>;
}) {
  const [others, setOthers] = useState<Trip[] | null>(null);
  const [from, setFrom] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    readAtlas()
      .then((atlas) => {
        const rest = atlas.trips.filter((one) => one.id !== trip.id).sort((a, b) => b.starts_on.localeCompare(a.starts_on));
        setOthers(rest);
        setFrom(rest[0]?.id ?? "");
      })
      .catch(() => setOthers([]));
  }, [trip.id]);

  return (
    <Sheet
      title={`Copiar la ${LISTS[list].toLowerCase()}`}
      onClose={onClose}
      action={{
        label: "Copiar",
        disabled: !from || busy,
        onClick: () => {
          setBusy(true);
          void onCopy(from).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        {others === null ? null : others.length === 0 ? (
          <Hint>No hay otro viaje del que copiar.</Hint>
        ) : (
          <>
            <SelectField
              label="De qué viaje"
              value={from}
              onChange={setFrom}
              options={others.map((one) => ({ value: one.id, label: `${one.title} · ${one.starts_on.slice(0, 4)}` }))}
            />
            <Hint>Se copia sin marcar, y lo que ya está en esta lista no se repite.</Hint>
          </>
        )}
      </div>
    </Sheet>
  );
}
