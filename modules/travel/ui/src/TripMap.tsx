import { Button, GroupLabel, Hint, Icon, Screen, SegmentedControl, SelectField, Skeleton } from "@openarga/ui";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import {
  type Block,
  type DayRoute,
  type Itinerary,
  type PlaceCategory,
  type Profile,
  type Stay,
  Unauthorised,
  moveBlock,
  readDayRoute,
  readDays,
  signIn,
} from "./api";
import type { Navigate } from "./App";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { Queued } from "./offline";
import { TripTabs } from "./TripChrome";
import { KINDS, MODES, PLACE_CATEGORIES, categoryOf, dayHue, dayLabel, distance, duration, hours, mapsLink } from "./words";

const StreetMap = lazy(() => import("@openarga/ui/street-map").then((found) => ({ default: found.StreetMap })));

const MAP_PADDING = { top: 72, bottom: 190, left: 40, right: 40 };

const PROFILES: { value: Profile; label: string }[] = [
  { value: "foot", label: "A pie" },
  { value: "bike", label: "Bici" },
  { value: "car", label: "Coche" },
];

export interface TripStop {
  id: string;
  lon: number;
  lat: number;
  number: number | null;
  title: string;
  hue: number;
  day: string | null;
  dayNumber: number;
  block: Block | null;
  stay: Stay | null;
  quiet?: boolean;
}

export function savedStops(itinerary: Itinerary, only: PlaceCategory | null = null): TripStop[] {
  return itinerary.unscheduled.flatMap((block) => {
    const place = block.place;
    if (!place || place.lat == null || place.lon == null) return [];
    if (only && (place.category ?? "other") !== only) return [];
    return [
      {
        id: block.id,
        lon: place.lon,
        lat: place.lat,
        number: null,
        title: block.title,
        hue: categoryOf(place).hue,
        day: null,
        dayNumber: 0,
        block,
        stay: null,
        quiet: true,
      },
    ];
  });
}

export function savedKinds(itinerary: Itinerary): { category: PlaceCategory; count: number }[] {
  const counts = new Map<PlaceCategory, number>();
  for (const block of itinerary.unscheduled) {
    const category = block.place?.category ?? "other";
    counts.set(category, (counts.get(category) ?? 0) + 1);
  }
  return (Object.keys(PLACE_CATEGORIES) as PlaceCategory[])
    .filter((category) => counts.has(category))
    .map((category) => ({ category, count: counts.get(category)! }));
}

export function tripStops(itinerary: Itinerary): TripStop[] {
  const found: TripStop[] = [];
  const homes = new Set<string>();
  for (const day of itinerary.days) {
    const hue = dayHue(day.number);
    const sleeping = day.sleeping;
    if (sleeping && sleeping.place.lat != null && sleeping.place.lon != null && !homes.has(sleeping.id)) {
      homes.add(sleeping.id);
      found.push({
        id: `stay-${sleeping.id}`,
        lon: sleeping.place.lon,
        lat: sleeping.place.lat,
        number: null,
        title: sleeping.accommodation ?? sleeping.place.name,
        hue,
        day: day.day,
        dayNumber: day.number,
        block: null,
        stay: sleeping,
      });
    }
    let number = 0;
    for (const item of day.items) {
      const block = item.block;
      if (!block?.place || block.place.lat == null || block.place.lon == null) continue;
      number += 1;
      found.push({
        id: block.id,
        lon: block.place.lon,
        lat: block.place.lat,
        number,
        title: block.title,
        hue,
        day: day.day,
        dayNumber: day.number,
        block,
        stay: null,
      });
    }
  }
  return found;
}

export function TripMapScreen({ id, navigate }: { id: string; navigate: Navigate }) {
  const loaded = useLoad<Itinerary>(`days/${id}`, () => readDays(id));
  const found = loaded.data;
  const setFound = loaded.set;
  const [problem, setProblem] = useState("");
  const [day, setDay] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>("foot");
  const [route, setRoute] = useState<DayRoute | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [panel, setPanel] = useState(false);
  const [showSaved, setShowSaved] = useState(true);
  const [only, setOnly] = useState<PlaceCategory | null>(null);

  const toDay = async (blockId: string, target: string) => {
    try {
      setFound(await moveBlock(id, blockId, target, 1000));
      setSelected(null);
    } catch (error) {
      if (error instanceof Queued) return setProblem(error.message);
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Error ? error.message : "No se ha podido llevar al día.");
    }
  };

  useEffect(() => {
    setRoute(null);
    if (!day) return;
    let current = true;
    readDayRoute(id, day, profile)
      .then((one) => current && setRoute(one))
      .catch(() => current && setRoute(null));
    return () => {
      current = false;
    };
  }, [id, day, profile]);

  const all = useMemo(() => (found ? tripStops(found) : []), [found]);
  const saved = useMemo(() => (found ? savedStops(found, only) : []), [found, only]);
  const shown = [...(day ? all.filter((one) => one.day === day) : all), ...(showSaved ? saved : [])];
  const chosen = found?.days.find((one) => one.day === day) ?? null;
  const open = [...all, ...saved].find((one) => one.id === selected) ?? null;
  const back = { label: "Viaje", onClick: () => navigate({ screen: "trip", id }) };

  if (!found) {
    return (
      <Screen>
        <ScreenHeader title="Mapa" back={back} />
        <Pending found={loaded.found} label="Cargando el mapa" />
      </Screen>
    );
  }

  const kinds = savedKinds(found);
  return (
    <main className="travel-whole-map-screen" data-panel={panel || undefined}>
      <ScreenHeader eyebrow={found.title} title={chosen ? (chosen.title ?? `Día ${chosen.number}`) : "Mapa"} back={back} />
      <TripTabs id={id} active="tripmap" navigate={navigate} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {all.length === 0 && saved.length === 0 ? (
        <Hint>Aún no hay sitios con lugar. Añade dónde duermes o lo que vas a ver, y aquí sale el viaje entero.</Hint>
      ) : (
        <div className="travel-whole-map-body">
        <SideList
          itinerary={found}
          day={day}
          selected={selected}
          onSelect={(stop, stopDay) => {
            if (stopDay !== day && stopDay !== null) setDay(stopDay);
            setSelected(stop);
          }}
        />
        <div className="travel-whole-map">
          <Suspense fallback={<Skeleton label="Cargando el mapa" />}>
            <StreetMap
              tiles="/api/travel/tiles/{z}/{x}/{y}"
              glyphs="/travel/map/"
              stops={shown}
              line={route?.line ?? null}
              lineHue={chosen ? dayHue(chosen.number) : undefined}
              padding={MAP_PADDING}
              selected={selected}
              onSelect={setSelected}
              label={chosen ? `Mapa del día ${chosen.number}` : `Mapa de ${found.title}`}
            />
          </Suspense>
          <div className="travel-whole-map-controls">
            {chosen && (
              <div className="travel-whole-map-route glass">
                <SegmentedControl label="Cómo te mueves" value={profile} onChange={setProfile} options={PROFILES} />
                {route && route.distance_m !== null && route.duration_s !== null && (
                  <span className="travel-whole-map-total">
                    {distance(route.distance_m)} · {duration(route.duration_s)}
                  </span>
                )}
              </div>
            )}
            <div className="travel-day-chips" role="group" aria-label="Qué día">
              <button
                type="button"
                className="travel-day-chip glass"
                aria-pressed={day === null}
                onClick={() => {
                  setDay(null);
                  setSelected(null);
                }}
              >
                Todos
              </button>
              {found.days.map((one) => (
                <button
                  key={one.day}
                  type="button"
                  className="travel-day-chip glass"
                  data-hue={dayHue(one.number)}
                  aria-pressed={day === one.day}
                  onClick={() => {
                    setDay(one.day);
                    setSelected(null);
                  }}
                >
                  Día {one.number} · {dayLabel(one.day)}
                </button>
              ))}
            </div>
          </div>
          {!panel && !open && (
          <button
            type="button"
            className="travel-saved-toggle glass"
            aria-expanded={panel}
            onClick={() => setPanel(!panel)}
          >
            <Icon name="bookmark" /> Guardados{found.unscheduled.length ? ` · ${found.unscheduled.length}` : ""}
          </button>
          )}
          {panel && (
            <SavedPanel
              itinerary={found}
              kinds={kinds}
              only={only}
              onOnly={setOnly}
              showSaved={showSaved}
              onShowSaved={setShowSaved}
              selected={selected}
              onSelect={setSelected}
              onClose={() => setPanel(false)}
            />
          )}
          {open && (
            <StopCard
              stop={open}
              days={found.days.map((one) => ({ value: one.day, label: `Día ${one.number} · ${dayLabel(one.day)}` }))}
              onClose={() => setSelected(null)}
              onDay={() => navigate({ screen: "days", id })}
              onToDay={(target) => open.block && void toDay(open.block.id, target)}
            />
          )}
        </div>
        </div>
      )}
    </main>
  );
}

function SideList({
  itinerary,
  day,
  selected,
  onSelect,
}: {
  itinerary: Itinerary;
  day: string | null;
  selected: string | null;
  onSelect: (id: string, day: string | null) => void;
}) {
  const days = day ? itinerary.days.filter((one) => one.day === day) : itinerary.days;
  return (
    <aside className="travel-side-list" aria-label="Día a día">
      {days.map((one) => (
        <section key={one.day} className="travel-side-day">
          <GroupLabel>
            <span className="travel-day-dot" data-hue={dayHue(one.number)} aria-hidden />
            Día {one.number} · {dayLabel(one.day)}
            {one.title && <span className="travel-side-day-name">{one.title}</span>}
          </GroupLabel>
          <ol className="travel-side-items">
            {one.items.map((item) => {
              const block = item.block;
              const located = Boolean(block?.place?.lat != null);
              const at = block?.starts_at ?? item.leg?.departs_at ?? (item.type === "check_out" ? item.stay?.check_out_at : item.stay?.check_in_at) ?? null;
              const title = block
                ? block.title
                : item.leg
                  ? `${item.leg.from_place.name} → ${item.leg.to_place.name}`
                  : `${item.type === "check_out" ? "Sales de" : "Llegas a"} ${item.stay?.accommodation ?? item.stay?.place.name ?? ""}`;
              const icon = block
                ? block.place
                  ? categoryOf(block.place).icon
                  : KINDS[block.kind].icon
                : item.leg
                  ? MODES[item.leg.mode].icon
                  : "home";
              const key = `${item.type}-${block?.id ?? item.leg?.id ?? item.stay?.id}`;
              return (
                <li key={key}>
                  <button
                    type="button"
                    className="travel-side-item"
                    data-selected={(block && block.id === selected) || undefined}
                    disabled={!located}
                    onClick={() => block && onSelect(block.id, one.day)}
                  >
                    <span className="travel-side-time">{at ? hours(at) : ""}</span>
                    <Icon name={icon} />
                    <span className="travel-side-text">{title}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </aside>
  );
}

function SavedPanel({
  itinerary,
  kinds,
  only,
  onOnly,
  showSaved,
  onShowSaved,
  selected,
  onSelect,
  onClose,
}: {
  itinerary: Itinerary;
  kinds: { category: PlaceCategory; count: number }[];
  only: PlaceCategory | null;
  onOnly: (category: PlaceCategory | null) => void;
  showSaved: boolean;
  onShowSaved: (show: boolean) => void;
  selected: string | null;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const groups = kinds
    .filter((one) => !only || one.category === only)
    .map((one) => ({
      ...one,
      blocks: itinerary.unscheduled.filter((block) => (block.place?.category ?? "other") === one.category),
    }));
  return (
    <aside className="travel-saved-panel surface" aria-label="Sitios guardados">
      <header className="travel-saved-head">
        <span className="travel-stop-card-title">Guardados</span>
        <button
          type="button"
          className="travel-day-chip"
          aria-pressed={showSaved}
          onClick={() => onShowSaved(!showSaved)}
        >
          En el mapa
        </button>
        <button type="button" className="travel-stop-card-close" aria-label="Cerrar" onClick={onClose}>
          <Icon name="close" />
        </button>
      </header>
      {kinds.length === 0 ? (
        <p className="travel-stop-card-notes">
          Nada guardado aún. Desde «Cerca» o al añadir algo sin día, se queda aquí esperando hueco.
        </p>
      ) : (
        <>
          <div className="travel-saved-kinds" role="group" aria-label="Qué tipo">
            {kinds.map((one) => (
              <button
                key={one.category}
                type="button"
                className="travel-day-chip"
                data-hue={PLACE_CATEGORIES[one.category].hue}
                aria-pressed={only === one.category}
                onClick={() => onOnly(only === one.category ? null : one.category)}
              >
                {PLACE_CATEGORIES[one.category].label} · {one.count}
              </button>
            ))}
          </div>
          <div className="travel-saved-list">
            {groups.map((group) => (
              <section key={group.category}>
                <GroupLabel>
                  <span className="travel-day-dot" data-hue={PLACE_CATEGORIES[group.category].hue} aria-hidden />
                  {PLACE_CATEGORIES[group.category].label}
                </GroupLabel>
                <ol className="travel-side-items">
                  {group.blocks.map((block) => (
                    <li key={block.id}>
                      <button
                        type="button"
                        className="travel-side-item"
                        data-selected={block.id === selected || undefined}
                        onClick={() => onSelect(block.id)}
                      >
                        <Icon name={categoryOf(block.place).icon} />
                        <span className="travel-side-text">
                          {block.title}
                          {block.notes && <span className="travel-side-note">{block.notes}</span>}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

function StopCard({
  stop,
  days,
  onClose,
  onDay,
  onToDay,
}: {
  stop: TripStop;
  days: { value: string; label: string }[];
  onClose: () => void;
  onDay: () => void;
  onToDay: (day: string) => void;
}) {
  const [target, setTarget] = useState(days[0]?.value ?? "");
  const block = stop.block;
  const place = block?.place ?? stop.stay?.place ?? null;
  const kind = block ? (block.place ? categoryOf(block.place) : { ...KINDS[block.kind], hue: stop.hue }) : null;
  return (
    <article className="travel-stop-card surface glass" aria-label={stop.title}>
      <header className="travel-stop-card-head">
        <span className="travel-step-mark" data-hue={kind?.hue ?? stop.hue}>
          <Icon name={kind?.icon ?? "home"} />
        </span>
        <span className="travel-step-text">
          <span className="travel-stop-card-kind">
            {[kind?.label ?? "Alojamiento", block?.starts_at && hours(block.starts_at, block.ends_at)].filter(Boolean).join(" · ")}
          </span>
          <span className="travel-stop-card-title">{stop.title}</span>
          <span className="travel-step-detail" data-hue={stop.day ? stop.hue : undefined}>
            {stop.day ? `Día ${stop.dayNumber} · ${dayLabel(stop.day)}` : "Guardado, sin día"}
          </span>
        </span>
        <button type="button" className="travel-stop-card-close" aria-label="Cerrar" onClick={onClose}>
          <Icon name="close" />
        </button>
      </header>
      {block?.notes && <p className="travel-stop-card-notes">{block.notes}</p>}
      {stop.day === null && days.length > 0 && (
        <div className="travel-stop-card-today">
          <SelectField label="A qué día" value={target} onChange={setTarget} options={days} hideLabel />
          <Button variant="primary" size="small" icon="calendar" onClick={() => onToDay(target)}>
            A un día
          </Button>
        </div>
      )}
      <div className="travel-actions">
        {stop.day !== null && (
          <Button variant="secondary" size="small" icon="list" onClick={onDay}>
            Ver en el día
          </Button>
        )}
        {place?.lat != null && place.lon != null && (
          <a
            className="travel-stop-card-maps"
            href={mapsLink(place.lat, place.lon, place.name)}
            target="_blank"
            rel="noreferrer"
          >
            <Icon name="external" /> Maps
          </a>
        )}
      </div>
    </article>
  );
}
