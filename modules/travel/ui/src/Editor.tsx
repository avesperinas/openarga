import {
  Button,
  CANNOT_UNDO,
  ChoiceChips,
  ConfirmDelete,
  DateField,
  ErrorState,
  Hint,
  IconButton,
  List,
  ListRow,
  Screen,
  SegmentedControl,
  SelectField,
  Skeleton,
  Stepper,
  Switch,
  TextField,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import {
  type Mode,
  type Place,
  type Status,
  type Trip,
  type TripIn,
  Unauthorised,
  addExpense,
  addLeg,
  addStay,
  addVisit,
  createTrip,
  deletePart,
  readTrip,
  signIn,
  updateLeg,
  updateTrip,
} from "./api";
import type { Navigate } from "./App";
import { drawn, orderedLegs } from "./atlas";
import { ScreenHeader } from "./Header";
import { ExpenseForm } from "./ExpenseForm";
import { PlacePicker } from "./PlacePicker";
import { CATEGORIES, MODES, dateRange, dayLabel, eurosExact, flag, km, nights, paidLine, todayIso } from "./words";

type Step = "data" | "stays" | "visits" | "legs" | "expenses";

const STEPS: { value: Step; label: string }[] = [
  { value: "data", label: "Datos" },
  { value: "stays", label: "Lugares" },
  { value: "visits", label: "Visitas" },
  { value: "legs", label: "Trayectos" },
  { value: "expenses", label: "Gastos" },
];

type Removal = { part: "stays" | "visits" | "legs" | "expenses"; id: string; subject: string; what: string };

export function EditorScreen({
  id,
  navigate,
  onChanged,
}: {
  id: string | null;
  navigate: Navigate;
  onChanged: () => void;
}) {
  const [trip, setTrip] = useState<Trip | null>(null);
  const [step, setStep] = useState<Step>("data");
  const [problem, setProblem] = useState("");
  const [removing, setRemoving] = useState<Removal | null>(null);

  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!id) {
      setTrip(null);
      setStep("data");
      return;
    }
    readTrip(id)
      .then(setTrip)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Error ? error.message : "No se ha podido leer el viaje.");
      });
  }, [id, attempt]);

  const apply = async (change: Promise<Trip>) => {
    setProblem("");
    try {
      const saved = await change;
      setTrip(saved);
      onChanged();
      return saved;
    } catch (error) {
      if (error instanceof Unauthorised) signIn();
      setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
      return null;
    }
  };

  const back = trip
    ? { label: trip.title, onClick: () => navigate({ screen: "trip", id: trip.id }) }
    : { label: "Viajes", onClick: () => navigate({ screen: "trips" }) };

  if (id && !trip) {
    return (
      <Screen>
        <ScreenHeader title="Editar viaje" back={back} />
        {problem ? (
          <ErrorState
            title="Travel no contesta"
            detail={problem}
            onRetry={() => {
              setProblem("");
              setAttempt((now) => now + 1);
            }}
          />
        ) : (
          <Skeleton label="Cargando el viaje" />
        )}
      </Screen>
    );
  }

  return (
    <Screen>
      <ScreenHeader
        eyebrow={trip ? dateRange(trip.starts_on, trip.ends_on) : undefined}
        title={trip ? trip.title : "Nuevo viaje"}
        back={back}
      />
      {trip && <ChoiceChips label="Paso" value={step} onChange={setStep} options={STEPS} />}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}

      {step === "data" && (
        <DataStep
          trip={trip}
          onSave={async (data) => {
            if (trip) {
              await apply(updateTrip(trip.id, data, trip.status === "plan"));
              return;
            }
            const created = await apply(createTrip(data));
            if (created) {
              navigate({ screen: "edit", id: created.id });
              setStep("stays");
            }
          }}
        />
      )}
      {trip && step === "stays" && (
        <StaysStep trip={trip} apply={apply} onRemove={setRemoving} onNext={() => setStep("visits")} />
      )}
      {trip && step === "visits" && (
        <VisitsStep trip={trip} apply={apply} onRemove={setRemoving} onNext={() => setStep("legs")} />
      )}
      {trip && step === "legs" && (
        <LegsStep trip={trip} apply={apply} onRemove={setRemoving} onNext={() => setStep("expenses")} />
      )}
      {trip && step === "expenses" && (
        <ExpensesStep
          trip={trip}
          apply={apply}
          onRemove={setRemoving}
          onDone={() => navigate({ screen: "trip", id: trip.id })}
        />
      )}

      {removing && trip && (
        <ConfirmDelete
          title={`¿Quitar ${removing.what}?`}
          subject={removing.subject}
          consequence={CANNOT_UNDO}
          action={`Quitar ${removing.what}`}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            const saved = await deletePart(trip.id, removing.part, removing.id);
            setTrip(saved);
            onChanged();
            setRemoving(null);
          }}
        />
      )}
    </Screen>
  );
}

type Apply = (change: Promise<Trip>) => Promise<Trip | null>;

const words = (text: string) =>
  text
    .split(",")
    .map((one) => one.trim())
    .filter(Boolean);

function DataStep({ trip, onSave }: { trip: Trip | null; onSave: (data: TripIn) => Promise<void> }) {
  const [title, setTitle] = useState(trip?.title ?? "");
  const [starts, setStarts] = useState(trip?.starts_on ?? "");
  const [ends, setEnds] = useState(trip?.ends_on ?? "");
  const [travellers, setTravellers] = useState<number | null>(trip?.travellers ?? 1);
  const [companions, setCompanions] = useState(trip?.companions.join(", ") ?? "");
  const [tags, setTags] = useState(trip?.tags.join(", ") ?? "");
  const [notes, setNotes] = useState(trip?.notes ?? "");
  const [budget, setBudget] = useState(trip?.budget_eur != null ? String(trip.budget_eur) : "");
  const amount = budget.trim().replace(",", ".");
  const badBudget = amount !== "" && !/^\d+(\.\d{1,2})?$/.test(amount);
  const [status, setStatus] = useState<Status | null>(null);
  const chosen: Status = status ?? (starts && starts > todayIso() ? "plan" : "confirmed");
  const [busy, setBusy] = useState(false);
  const backwards = Boolean(starts && ends && ends < starts);
  const ready = title.trim() && starts && ends && !backwards && !badBudget && !busy;

  return (
    <form
      className="surface travel-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ready) return;
        setBusy(true);
        void onSave({
          title: title.trim(),
          starts_on: starts,
          ends_on: ends,
          travellers: travellers ?? 1,
          companions: words(companions),
          tags: words(tags),
          notes: notes.trim() || null,
          budget_eur: amount || null,
          ...(trip ? {} : { status: chosen }),
        }).finally(() => setBusy(false));
      }}
    >
      <TextField label="Título" value={title} onChange={setTitle} placeholder="Flandes en primavera" />
      <div className="travel-form-row">
        <DateField label="Primer día" value={starts} onChange={setStarts} />
        <DateField
          label="Último día"
          value={ends}
          onChange={setEnds}
          invalid={backwards}
          hint={backwards ? "Acaba antes de empezar" : undefined}
        />
      </div>
      <div className="travel-field">
        <span className="travel-field-label">Viajeros</span>
        <Stepper label="Viajeros" value={travellers} onChange={setTravellers} min={1} max={50} step={1} />
      </div>
      <TextField label="Con quién" value={companions} onChange={setCompanions} hint="Separados por comas" />
      <TextField label="Etiquetas" value={tags} onChange={setTags} hint="Escapada, trabajo, verano…" />
      <TextField label="Notas" value={notes} onChange={setNotes} />
      <TextField
        label="Presupuesto por persona, en euros"
        inputMode="decimal"
        value={budget}
        onChange={setBudget}
        invalid={badBudget}
        hint={badBudget ? "Un importe como 900 o 900,50" : "Opcional: lo que quieres gastar"}
      />
      {!trip && (
        <>
          <SegmentedControl
            label="Estado"
            value={chosen}
            onChange={setStatus}
            options={[
              { value: "plan", label: "Plan" },
              { value: "confirmed", label: "Confirmado" },
            ]}
          />
          <Hint>
            {chosen === "plan"
              ? "Un plan se queda en Travel, con fechas que pueden moverse, hasta que lo confirmes."
              : "Confirmado sale en tu calendario."}
          </Hint>
        </>
      )}
      <Button type="submit" variant="primary" disabled={!ready}>
        {trip ? "Guardar datos" : "Crear viaje"}
      </Button>
    </form>
  );
}

function StaysStep({
  trip,
  apply,
  onRemove,
  onNext,
}: {
  trip: Trip;
  apply: Apply;
  onRemove: (removal: Removal) => void;
  onNext: () => void;
}) {
  const last = trip.stays.at(-1);
  const [place, setPlace] = useState<Place | null>(null);
  const [arrives, setArrives] = useState(last?.leaves_on ?? trip.starts_on);
  const [leaves, setLeaves] = useState(trip.ends_on);
  const [accommodation, setAccommodation] = useState("");

  useEffect(() => {
    setArrives(trip.stays.at(-1)?.leaves_on ?? trip.starts_on);
    setLeaves(trip.ends_on);
  }, [trip]);

  return (
    <>
      <Hint>Donde dormiste, en orden. Las noches son los días entre llegar y salir.</Hint>
      {trip.stays.length > 0 && (
        <List>
          {trip.stays.map((stay) => (
            <ListRow
              key={stay.id}
              title={`${flag(stay.place.country_code)} ${stay.place.name}`}
              detail={`${dateRange(stay.arrives_on, stay.leaves_on)} · ${nights(stay.nights)}${stay.accommodation ? ` · ${stay.accommodation}` : ""}`}
              accessory="trash"
              onClick={() =>
                onRemove({ part: "stays", id: stay.id, subject: stay.place.name, what: "lugar principal" })
              }
            />
          ))}
        </List>
      )}
      <div className="surface travel-form">
        {place ? (
          <>
            <ListRow
              title={`${flag(place.country_code)} ${place.name}`}
              detail={[place.region, place.country].filter(Boolean).join(", ") || "Sin situar en el mapa"}
              accessory="close"
              onClick={() => setPlace(null)}
            />
            <div className="travel-form-row">
              <DateField label="Llegada" value={arrives} onChange={setArrives} />
              <DateField label="Salida" value={leaves} onChange={setLeaves} />
            </div>
            <TextField
              label="Alojamiento"
              value={accommodation}
              onChange={setAccommodation}
              placeholder="Hotel, apartamento, casa de amigos…"
            />
            <Button
              variant="primary"
              icon="plus"
              disabled={!arrives || !leaves || leaves < arrives}
              onClick={async () => {
                const saved = await apply(
                  addStay(trip.id, {
                    place_id: place.id,
                    arrives_on: arrives,
                    leaves_on: leaves,
                    accommodation: accommodation.trim() || null,
                  }),
                );
                if (saved) {
                  setPlace(null);
                  setAccommodation("");
                }
              }}
            >
              Añadir lugar principal
            </Button>
          </>
        ) : (
          <PlacePicker label="Lugar principal" onPick={setPlace} />
        )}
      </div>
      <Button variant="secondary" onClick={onNext}>
        Siguiente: visitas
      </Button>
    </>
  );
}

function VisitsStep({
  trip,
  apply,
  onRemove,
  onNext,
}: {
  trip: Trip;
  apply: Apply;
  onRemove: (removal: Removal) => void;
  onNext: () => void;
}) {
  const [place, setPlace] = useState<Place | null>(null);
  const [day, setDay] = useState("");
  const [stay, setStay] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!day) return;
    const covering = trip.stays.find((one) => one.arrives_on <= day && day <= one.leaves_on);
    if (covering) setStay(covering.id);
  }, [day, trip.stays]);

  return (
    <>
      <Hint>Lo que viste sin dormir allí: una excursión, un museo, una playa. Se pinta en tono suave.</Hint>
      {trip.visits.length > 0 && (
        <List>
          {trip.visits.map((visit) => (
            <ListRow
              key={visit.id}
              title={`${flag(visit.place.country_code)} ${visit.place.name}`}
              detail={[visit.visited_on && dayLabel(visit.visited_on), visit.note].filter(Boolean).join(" · ") || undefined}
              accessory="trash"
              onClick={() => onRemove({ part: "visits", id: visit.id, subject: visit.place.name, what: "visita" })}
            />
          ))}
        </List>
      )}
      <div className="surface travel-form">
        {place ? (
          <>
            <ListRow
              title={`${flag(place.country_code)} ${place.name}`}
              detail={[place.region, place.country].filter(Boolean).join(", ") || "Sin situar en el mapa"}
              accessory="close"
              onClick={() => setPlace(null)}
            />
            <DateField label="Día" value={day} onChange={setDay} />
            {trip.stays.length > 0 && (
              <SelectField
                label="Desde"
                value={stay}
                onChange={setStay}
                options={[
                  { value: "", label: "Ninguno" },
                  ...trip.stays.map((one) => ({ value: one.id, label: one.place.name })),
                ]}
              />
            )}
            <TextField label="Nota" value={note} onChange={setNote} />
            <Button
              variant="primary"
              icon="plus"
              onClick={async () => {
                const saved = await apply(
                  addVisit(trip.id, {
                    place_id: place.id,
                    stay_id: stay || null,
                    visited_on: day || null,
                    note: note.trim() || null,
                  }),
                );
                if (saved) {
                  setPlace(null);
                  setNote("");
                }
              }}
            >
              Añadir visita
            </Button>
          </>
        ) : (
          <PlacePicker label="Lugar visitado" onPick={setPlace} />
        )}
      </div>
      <Button variant="secondary" onClick={onNext}>
        Siguiente: trayectos
      </Button>
    </>
  );
}

function LegsStep({
  trip,
  apply,
  onRemove,
  onNext,
}: {
  trip: Trip;
  apply: Apply;
  onRemove: (removal: Removal) => void;
  onNext: () => void;
}) {
  const known = new Map<string, Place>();
  for (const one of [...trip.stays.map((s) => s.place), ...trip.legs.flatMap((l) => [l.from_place, l.to_place])]) {
    known.set(one.id, one);
  }
  const [extra, setExtra] = useState<Place[]>([]);
  extra.forEach((one) => known.set(one.id, one));
  const places = [...known.values()];
  const firstStay = trip.stays[0]?.place.id ?? "";
  const [from, setFrom] = useState("");
  const [to, setTo] = useState(firstStay);
  const [mode, setMode] = useState<Mode>("plane");
  const [day, setDay] = useState(trip.starts_on);
  const [adding, setAdding] = useState(false);

  return (
    <>
      <Hint>
        Cómo fuiste de un sitio a otro. La ida sale de casa: añádela como otro sitio. Los kilómetros se calculan solos.
        El interruptor dice si sale en el mapa, la miniatura y el recorrido.
      </Hint>
      {trip.legs.length > 0 && (
        <ul className="surface travel-legs">
          {orderedLegs(trip).map((leg) => {
            const name = `${leg.from_place.name} → ${leg.to_place.name}`;
            return (
              <li key={leg.id} className="travel-leg">
                <span className="travel-leg-text">
                  <span className="travel-leg-title">{name}</span>
                  <span className="travel-step-detail">
                    {[MODES[leg.mode].label, leg.km !== null ? km(leg.km) : null, leg.travelled_on && dayLabel(leg.travelled_on)]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <Switch
                  label={`${name} en el mapa`}
                  checked={drawn(trip, leg)}
                  onChange={(on) =>
                    apply(
                      updateLeg(trip.id, leg.id, {
                        from_place_id: leg.from_place.id,
                        to_place_id: leg.to_place.id,
                        mode: leg.mode,
                        travelled_on: leg.travelled_on,
                        note: leg.note,
                        on_map: on,
                      }),
                    )
                  }
                />
                <IconButton
                  icon="trash"
                  label={`Quitar ${name}`}
                  variant="plain"
                  onClick={() => onRemove({ part: "legs", id: leg.id, subject: name, what: "trayecto" })}
                />
              </li>
            );
          })}
        </ul>
      )}
      <div className="surface travel-form">
        <SelectField
          label="Desde"
          value={from}
          onChange={setFrom}
          options={[{ value: "", label: "Elige…" }, ...places.map((one) => ({ value: one.id, label: one.name }))]}
        />
        <SelectField
          label="Hasta"
          value={to}
          onChange={setTo}
          options={[{ value: "", label: "Elige…" }, ...places.map((one) => ({ value: one.id, label: one.name }))]}
        />
        {adding ? (
          <PlacePicker
            label="Otro sitio"
            onPick={(place) => {
              setExtra((now) => [...now, place]);
              if (!from) setFrom(place.id);
              else setTo(place.id);
              setAdding(false);
            }}
          />
        ) : (
          <Button variant="plain" icon="plus" onClick={() => setAdding(true)}>
            Otro sitio, como casa
          </Button>
        )}
        <ChoiceChips<Mode>
          label="Medio"
          value={mode}
          onChange={setMode}
          options={(Object.keys(MODES) as Mode[]).map((one) => ({ value: one, label: MODES[one].label }))}
        />
        <DateField label="Día" value={day} onChange={setDay} />
        <Button
          variant="primary"
          icon="plus"
          disabled={!from || !to || from === to}
          onClick={async () => {
            const saved = await apply(
              addLeg(trip.id, { from_place_id: from, to_place_id: to, mode, travelled_on: day || null }),
            );
            if (saved) {
              const stops = saved.stays.map((one) => one.place.id);
              const after = stops[stops.indexOf(to) + 1];
              setFrom(to);
              setTo(after ?? "");
              const arrived = saved.stays.find((one) => one.place.id === to);
              if (arrived) setDay(arrived.leaves_on);
            }
          }}
        >
          Añadir trayecto
        </Button>
      </div>
      <Button variant="secondary" onClick={onNext}>
        Siguiente: gastos
      </Button>
    </>
  );
}

function ExpensesStep({
  trip,
  apply,
  onRemove,
  onDone,
}: {
  trip: Trip;
  apply: Apply;
  onRemove: (removal: Removal) => void;
  onDone: () => void;
}) {
  const [needsRate, setNeedsRate] = useState(false);

  return (
    <>
      {trip.expenses.length > 0 && (
        <List>
          {trip.expenses.map((expense) => (
            <ListRow
              key={expense.id}
              title={expense.concept}
              subtitle={paidLine(expense) ?? CATEGORIES[expense.category]}
              value={eurosExact(expense.amount_eur)}
              detail={expense.note ?? undefined}
              accessory="trash"
              onClick={() => onRemove({ part: "expenses", id: expense.id, subject: expense.concept, what: "gasto" })}
            />
          ))}
        </List>
      )}
      <ExpenseForm
        trip={trip}
        needsRate={needsRate}
        onSave={async (expense) => {
          const saved = await apply(addExpense(trip.id, expense));
          setNeedsRate(!saved && Boolean(expense.currency));
          return saved !== null;
        }}
      />
      <Hint>
        {eurosExact(trip.spend.per_person)} por persona · {eurosExact(trip.spend.group)} el grupo
        {trip.spend.per_day !== null && ` · ${eurosExact(trip.spend.per_day)} al día`}
      </Hint>
      <Button variant="primary" onClick={onDone}>
        Hecho
      </Button>
    </>
  );
}

