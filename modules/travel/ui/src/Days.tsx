import { mutate } from "@openarga/app";
import {
  Button,
  CANNOT_UNDO,
  ChoiceChips,
  ConfirmDelete,
  GroupLabel,
  Hint,
  Icon,
  Screen,
  SelectField,
  Sheet,
  TextField,
} from "@openarga/ui";
import { type PointerEvent as ReactPointerEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import {
  type Block,
  type BlockIn,
  type Day,
  type DayItem,
  type ForecastDay,
  type Itinerary,
  type Kind,
  type Place,
  type PlaceCategory,
  Unauthorised,
  addBlock,
  readForecast,
  moveBlock,
  readDays,
  removeBlock,
  savePlace,
  setDayTitle,
  setPlaceCategory,
  signIn,
  updateBlock,
} from "./api";
import type { Navigate } from "./App";
import { ScreenHeader } from "./Header";
import { type Around, NearbySheet } from "./Nearby";
import { Pending, useLoad } from "./Loads";
import { Queued } from "./offline";
import { PlacePicker } from "./PlacePicker";
import { type Slot, blocksOf, moved, stepped } from "./reorder";
import { TripTabs } from "./TripChrome";
import { dayLine } from "./weather";
import {
  KINDS,
  MODES,
  PLACE_CATEGORIES,
  categoryOf,
  dateRange,
  dayHue,
  dayLabel,
  daysBetween,
  flag,
  hours,
  mapsLink,
} from "./words";

type Editing = { block: Block | null; slot: Slot };
type Drag = { id: string; from: Slot; startY: number; dy: number; maxScroll: number };
type Target = { slot: Slot; index: number };

export function DaysScreen({ id, navigate }: { id: string; navigate: Navigate }) {
  const key = `days/${id}`;
  const loaded = useLoad<Itinerary>(key, () => readDays(id));
  const found = loaded.data;
  const setFound = (next: Itinerary) => void mutate(key, next);
  const [problem, setProblem] = useState("");
  const [editing, setEditing] = useState<Editing | null>(null);
  const [titling, setTitling] = useState<{ day: string; number: number; title: string } | null>(null);
  const [near, setNear] = useState<Around | null>(null);
  const [forecast, setForecast] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!found) return;
    const places = new Map<string, [number, number]>();
    for (const day of found.days) {
      const place = day.sleeping?.place;
      if (place?.lat != null && place.lon != null) places.set(`${place.lat.toFixed(2)},${place.lon.toFixed(2)}`, [place.lat, place.lon]);
    }
    let current = true;
    void Promise.all(
      [...places.entries()].slice(0, 4).map(async ([key, [lat, lon]]): Promise<[string, ForecastDay[]]> => {
        try {
          return [key, (await readForecast(lat, lon)).weather?.days ?? []];
        } catch {
          return [key, []];
        }
      }),
    ).then((answers) => {
      if (!current) return;
      const byPlace = new Map(answers);
      const lines: Record<string, string> = {};
      for (const day of found.days) {
        const place = day.sleeping?.place;
        if (place?.lat == null || place.lon == null) continue;
        const match = byPlace.get(`${place.lat.toFixed(2)},${place.lon.toFixed(2)}`)?.find((one) => one.day === day.day);
        if (match) lines[day.day] = dayLine(match);
      }
      setForecast(lines);
    });
    return () => {
      current = false;
    };
  }, [found?.trip_id, found?.days.map((day) => day.sleeping?.id ?? "").join()]);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const lists = useRef(new Map<string, HTMLOListElement>());

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
  }, []);

  const apply = useCallback(
    async (change: Promise<Itinerary>) => {
      try {
        loaded.set(await change);
        setProblem("");
        return true;
      } catch (error) {
        if (error instanceof Queued) {
          setProblem(error.message);
          return true;
        }
        fail(error);
        void loaded.found.refresh();
        return false;
      }
    },
    [loaded, fail],
  );

  const place = (blockId: string, slot: Slot, index: number) => {
    if (!found) return;
    setFound(moved(found, blockId, slot, index));
    void apply(moveBlock(id, blockId, slot, index));
  };

  const back = { label: "Viaje", onClick: () => navigate({ screen: "trip", id }) };
  if (!found) {
    return (
      <Screen>
        <ScreenHeader title="Día a día" back={back} />
        <Pending found={loaded.found} label="Cargando el itinerario" />
      </Screen>
    );
  }

  const keyOf = (slot: Slot) => slot ?? "";

  const targetAt = (y: number, dragged: string): Target | null => {
    let best: { slot: Slot; list: HTMLOListElement; distance: number } | null = null;
    for (const [key, list] of lists.current) {
      const box = list.getBoundingClientRect();
      const distance = y < box.top ? box.top - y : y > box.bottom ? y - box.bottom : 0;
      if (!best || distance < best.distance) best = { slot: key === "" ? null : key, list, distance };
    }
    if (!best) return null;
    const rows = Array.from(best.list.querySelectorAll<HTMLElement>("[data-block]")).filter(
      (row) => row.dataset.block !== dragged,
    );
    const index = rows.findIndex((row) => {
      const box = row.getBoundingClientRect();
      return y < box.top + box.height / 2;
    });
    return { slot: best.slot, index: index < 0 ? rows.length : index };
  };

  const grab = (event: ReactPointerEvent<HTMLButtonElement>, block: Block) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      id: block.id,
      from: block.day,
      startY: event.clientY + window.scrollY,
      dy: 0,
      maxScroll: document.documentElement.scrollHeight - window.innerHeight,
    });
  };
  const follow = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!drag) return;
    setDrag({ ...drag, dy: event.clientY + window.scrollY - drag.startY });
    setTarget(targetAt(event.clientY, drag.id));
    const edge = 72;
    if (event.clientY < edge) window.scrollBy(0, -12);
    else if (event.clientY > window.innerHeight - edge && window.scrollY < drag.maxScroll) {
      window.scrollBy(0, Math.min(12, drag.maxScroll - window.scrollY));
    }
  };
  const drop = () => {
    if (drag && target) place(drag.id, target.slot, target.index);
    setDrag(null);
    setTarget(null);
  };
  const step = (block: Block, direction: -1 | 1) => {
    const next = stepped(found, block.id, direction);
    if (next) place(block.id, next.slot, next.index);
  };

  const row = (block: Block) => (
    <li
      key={block.id}
      data-block={block.id}
      className="travel-block"
      data-dragging={drag?.id === block.id || undefined}
      style={drag?.id === block.id ? { transform: `translateY(${drag.dy}px)` } : undefined}
    >
      <button
        type="button"
        className="travel-block-handle"
        aria-label={`Mover ${block.title}. Flechas arriba y abajo.`}
        onPointerDown={(event) => grab(event, block)}
        onPointerMove={follow}
        onPointerUp={drop}
        onPointerCancel={() => {
          setDrag(null);
          setTarget(null);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            event.preventDefault();
            step(block, event.key === "ArrowUp" ? -1 : 1);
          }
        }}
      >
        <Icon name="list" />
      </button>
      <button type="button" className="travel-block-body" onClick={() => setEditing({ block, slot: block.day })}>
        {block.place ? (
          <span className="travel-step-mark" data-hue={categoryOf(block.place).hue}>
            <Icon name={categoryOf(block.place).icon} label={categoryOf(block.place).label} />
          </span>
        ) : (
          <span className="travel-step-mark" data-kind={block.kind}>
            <Icon name={KINDS[block.kind].icon} />
          </span>
        )}
        <span className="travel-step-text">
          <span className="travel-step-title">
            {block.starts_at && <span className="travel-block-time">{hours(block.starts_at, block.ends_at)} </span>}
            {block.title}
          </span>
          {(block.place || block.notes || block.confirmation) && (
            <span className="travel-step-detail">
              {[
                block.place &&
                  `${flag(block.place.country_code)}${block.place.name === block.title ? "" : ` ${block.place.name}`}`,
                block.notes,
                block.confirmation && `Reserva ${block.confirmation}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          )}
        </span>
      </button>
      {block.place?.lat != null && block.place.lon != null && (
        <a
          className="travel-block-maps"
          href={mapsLink(block.place.lat, block.place.lon, block.place.name)}
          target="_blank"
          rel="noreferrer"
          aria-label={`Abrir ${block.place.name} en Maps`}
        >
          <Icon name="external" />
        </a>
      )}
    </li>
  );

  const list = (slot: Slot, items: DayItem[] | null, around: Around | null = null) => {
    const blocks = blocksOf(found, slot);
    const ordered: DayItem[] = items ?? blocks.map((block) => ({ type: "block", stay: null, leg: null, block }));
    const fixed = ordered.filter((item) => !item.block);
    const marker = target && target.slot === slot && drag ? target.index : -1;
    const rows: ReactNode[] = [];
    let index = 0;
    for (const item of ordered) {
      if (!item.block) {
        rows.push(<FixedItem key={`${item.type}-${item.stay?.id ?? item.leg?.id}`} item={item} />);
        continue;
      }
      const block = item.block;
      if (block.id !== drag?.id && index === marker) rows.push(<li key="drop" className="travel-drop" aria-hidden />);
      rows.push(row(block));
      if (block.id !== drag?.id) index += 1;
    }
    if (marker === index && marker >= 0) rows.push(<li key="drop" className="travel-drop" aria-hidden />);
    return (
      <ol
        className="surface travel-day"
        ref={(element) => {
          if (element) lists.current.set(keyOf(slot), element);
          else lists.current.delete(keyOf(slot));
        }}
      >
        {rows}
        {blocks.length === 0 && fixed.length === 0 && marker < 0 && (
          <li className="travel-day-empty">{slot === null ? "Nada guardado sin día" : "Nada aún"}</li>
        )}
        <li className="travel-day-add">
          <Button variant="plain" size="small" icon="plus" onClick={() => setEditing({ block: null, slot })}>
            Añadir
          </Button>
          {slot !== null && (
            <Button variant="plain" size="small" icon="map" onClick={() => navigate({ screen: "day", id, day: slot })}>
              Mapa
            </Button>
          )}
          {around && (
            <Button variant="plain" size="small" icon="search" onClick={() => setNear(around)}>
              Cerca
            </Button>
          )}
        </li>
      </ol>
    );
  };

  const first = found.days[0]?.day;
  const last = found.days.at(-1)?.day;
  return (
    <Screen>
      <div className="travel-days" data-dragging={drag ? true : undefined}>
      <ScreenHeader
        eyebrow={first && last ? dateRange(first, last) : undefined}
        title={found.title}
        back={back}
      />
      <TripTabs id={id} active="days" navigate={navigate} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {found.days.map((day) => (
        <section key={day.day} className="travel-group">
          <GroupLabel>
            <span className="travel-day-dot" data-hue={dayHue(day.number)} aria-hidden />
            Día {day.number} · {dayLabel(day.day)}
            {(day.sleeping || forecast[day.day]) && (
              <span className="travel-group-detail">
                {[day.sleeping && `Duermes en ${day.sleeping.place.name}`, forecast[day.day]].filter(Boolean).join(" · ")}
              </span>
            )}
          </GroupLabel>
          <button
            type="button"
            className="travel-day-title"
            data-empty={day.title ? undefined : true}
            onClick={() => setTitling({ day: day.day, number: day.number, title: day.title ?? "" })}
          >
            {day.title ?? "Ponle título al día"}
          </button>
          {list(day.day, day.items, aroundOf(day))}
        </section>
      ))}
      <section className="travel-group">
        <GroupLabel>
          Sin día
          <span className="travel-group-detail">Lo que quieres ver, esperando hueco</span>
        </GroupLabel>
        {list(null, null)}
      </section>

      {titling && (
        <Sheet
          title={`Día ${titling.number}`}
          onClose={() => setTitling(null)}
          action={{
            label: "Guardar",
            onClick: async () => {
              if (await apply(setDayTitle(id, titling.day, titling.title.trim()))) setTitling(null);
            },
          }}
        >
          <TextField
            label="Título"
            value={titling.title}
            onChange={(title) => setTitling({ ...titling, title: title.slice(0, 80) })}
            placeholder="Llegada y casco antiguo"
            hint="Vacío, el día se queda sin título"
            autoFocus
          />
        </Sheet>
      )}
      {editing && (
        <BlockSheet
          editing={editing}
          days={found.days.map((day) => ({ value: day.day, label: `Día ${day.number} · ${dayLabel(day.day)}` }))}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            const saved = editing.block
              ? await apply(updateBlock(id, editing.block.id, data))
              : await apply(addBlock(id, { ...data, id: crypto.randomUUID() }));
            if (saved) setEditing(null);
          }}
          onRemove={async () => {
            if (editing.block && (await apply(removeBlock(id, editing.block.id)))) setEditing(null);
          }}
          onNearby={
            editing.block?.place?.lat != null && editing.block.place.lon != null
              ? () => {
                  const place = editing.block!.place!;
                  const day = found.days.find((one) => one.day === editing.block!.day);
                  setNear({
                    lat: place.lat!,
                    lon: place.lon!,
                    label: editing.block!.title,
                    day: day?.day ?? null,
                    dayLabel: day ? `Al día ${day.number}` : null,
                  });
                  setEditing(null);
                }
              : undefined
          }
        />
      )}
      {near && (
        <NearbySheet
          around={near}
          onClose={() => setNear(null)}
          onKeep={async (place, day) => {
            try {
              const saved = await savePlace(place);
              return apply(
                addBlock(id, {
                  id: crypto.randomUUID(),
                  day,
                  kind: place.group === "food" ? "meal" : "activity",
                  title: place.name.slice(0, 120),
                  starts_at: null,
                  ends_at: null,
                  place_id: saved.id,
                  notes: null,
                }),
              );
            } catch (error) {
              fail(error);
              return false;
            }
          }}
        />
      )}
      </div>
    </Screen>
  );
}

function aroundOf(day: Day): Around | null {
  const block = day.items.find((item) => item.block?.place?.lat != null)?.block;
  const place = day.sleeping?.place.lat != null ? day.sleeping.place : block?.place;
  if (!place || place.lat == null || place.lon == null) return null;
  const label = day.sleeping?.place.lat != null ? (day.sleeping.accommodation ?? day.sleeping.place.name) : place.name;
  return { lat: place.lat, lon: place.lon, label, day: day.day, dayLabel: `Al día ${day.number}` };
}

function FixedItem({ item }: { item: DayItem }) {
  if (item.leg) {
    const mode = MODES[item.leg.mode];
    return (
      <li className="travel-block travel-block-fixed">
        <span className="travel-step-mark">
          <Icon name={mode.icon} />
        </span>
        <span className="travel-step-text">
          <span className="travel-step-title">
            {item.leg.departs_at && <span className="travel-block-time">{hours(item.leg.departs_at)} </span>}
            {item.leg.from_place.name} → {item.leg.to_place.name}
          </span>
          <span className="travel-step-detail">
            {[
              item.leg.arrives_at &&
                `llega ${hours(item.leg.arrives_at)}` +
                  (item.leg.arrives_on && item.leg.arrives_on !== item.leg.travelled_on
                    ? ` (+${daysBetween(item.leg.travelled_on ?? item.leg.arrives_on, item.leg.arrives_on)})`
                    : ""),
              mode.label,
              [item.leg.carrier, item.leg.number].filter(Boolean).join(" ") || null,
              item.leg.seat && `asiento ${item.leg.seat}`,
              item.leg.confirmation,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </span>
      </li>
    );
  }
  if (!item.stay) return null;
  const leaving = item.type === "check_out";
  return (
    <li className="travel-block travel-block-fixed" data-kind="stay">
      <span className="travel-step-mark">
        <Icon name="home" />
      </span>
      <span className="travel-step-text">
        <span className="travel-step-title">
          {(leaving ? item.stay.check_out_at : item.stay.check_in_at) && (
            <span className="travel-block-time">{hours((leaving ? item.stay.check_out_at : item.stay.check_in_at)!)} </span>
          )}
          {leaving ? "Sales de" : "Llegas a"} {item.stay.place.name}
        </span>
        {(item.stay.accommodation || item.stay.confirmation) && (
          <span className="travel-step-detail">
            {[
              item.stay.accommodation,
              item.stay.confirmation,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        )}
      </span>
    </li>
  );
}

const CATEGORY_OPTIONS = (Object.keys(PLACE_CATEGORIES) as PlaceCategory[]).map((value) => ({
  value,
  label: PLACE_CATEGORIES[value].label,
}));
const KIND_OPTIONS = (Object.keys(KINDS) as Kind[]).map((kind) => ({ value: kind, label: KINDS[kind].label }));
const NO_DAY = "sin-dia";

function BlockSheet({
  editing,
  days,
  onClose,
  onSave,
  onRemove,
  onNearby,
}: {
  editing: Editing;
  days: { value: string; label: string }[];
  onClose: () => void;
  onSave: (data: BlockIn) => Promise<void>;
  onRemove: () => Promise<void>;
  onNearby?: () => void;
}) {
  const block = editing.block;
  const [title, setTitle] = useState(block?.title ?? "");
  const [kind, setKind] = useState<Kind>(block?.kind ?? "activity");
  const [day, setDay] = useState(editing.slot ?? NO_DAY);
  const [starts, setStarts] = useState(block?.starts_at?.slice(0, 5) ?? "");
  const [ends, setEnds] = useState(block?.ends_at?.slice(0, 5) ?? "");
  const [place, setPlace] = useState<Place | null>(block?.place ?? null);
  const [category, setCategory] = useState<PlaceCategory>(block?.place?.category ?? "other");
  const [picking, setPicking] = useState(false);
  const [notes, setNotes] = useState(block?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const backwards = Boolean(starts && ends && ends < starts);
  const ready = title.trim().length > 0 && !backwards && !busy;

  if (removing && block) {
    return (
      <ConfirmDelete
        title="¿Quitar del itinerario?"
        subject={block.title}
        consequence={block.visit_id ? `Deja de contar como visitado. ${CANNOT_UNDO}` : CANNOT_UNDO}
        action="Quitar"
        onCancel={() => setRemoving(false)}
        onConfirm={onRemove}
      />
    );
  }

  return (
    <Sheet
      title={block ? "Editar" : "Añadir al día"}
      onClose={onClose}
      action={{
        label: block ? "Guardar" : "Añadir",
        disabled: !ready,
        onClick: () => {
          setBusy(true);
          const typed =
            place && category !== (place.category ?? "other")
              ? setPlaceCategory(place.id, category).catch(() => undefined)
              : Promise.resolve();
          void typed.then(() => onSave({
            day: day === NO_DAY ? null : day,
            kind,
            title: title.trim(),
            starts_at: starts || null,
            ends_at: starts && ends ? ends : null,
            place_id: place?.id ?? null,
            notes: notes.trim() || null,
          })).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        <TextField label="Qué" value={title} onChange={setTitle} placeholder="Museo, comida, paseo…" autoFocus />
        <ChoiceChips label="Tipo" value={kind} onChange={setKind} options={KIND_OPTIONS} />
        <SelectField label="Día" value={day} onChange={setDay} options={[...days, { value: NO_DAY, label: "Sin día" }]} />
        <div className="travel-form-row">
          <TextField label="Empieza" type="time" value={starts} onChange={setStarts} />
          <TextField
            label="Acaba"
            type="time"
            value={ends}
            onChange={setEnds}
            invalid={backwards}
            hint={backwards ? "Acaba antes de empezar" : undefined}
          />
        </div>
        {place && !picking ? (
          <div className="travel-field">
            <span className="travel-field-label">Dónde</span>
            <span className="travel-block-place">
              {flag(place.country_code)} {place.name}
              <Button variant="plain" size="small" onClick={() => setPicking(true)}>
                Cambiar
              </Button>
              <Button variant="plain" size="small" onClick={() => setPlace(null)}>
                Quitar
              </Button>
            </span>
          </div>
        ) : (
          <PlacePicker
            label="Dónde"
            onPick={(chosen) => {
              setPlace(chosen);
              setCategory(chosen.category ?? "other");
              setPicking(false);
              if (!title.trim()) setTitle(chosen.name);
            }}
          />
        )}
        {place && (
          <ChoiceChips label="Qué sitio es" value={category} onChange={setCategory} options={CATEGORY_OPTIONS} />
        )}
        {kind === "activity" && place && <Hint>Cuenta como visitado y sale en el mapa.</Hint>}
        <TextField label="Notas" value={notes} onChange={setNotes} placeholder="Qué llevar, reservas…" />
        {onNearby && (
          <Button variant="secondary" icon="search" onClick={onNearby}>
            Qué hay cerca
          </Button>
        )}
        {block && (
          <Button variant="destructive" icon="trash" onClick={() => setRemoving(true)}>
            Quitar del itinerario
          </Button>
        )}
      </div>
    </Sheet>
  );
}
