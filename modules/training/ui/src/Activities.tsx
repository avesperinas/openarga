import {
  Button,
  Card,
  ChoiceChips,
  ConfirmDelete,
  DateField,
  Elapsed,
  Hint,
  Inline,
  isoDay,
  List,
  ListRow,
  Sheet,
  TextField,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { WorkoutPulseCard } from "./Pulse";
import {
  type Activity,
  type ActivityType,
  createActivityType,
  finishActivity,
  listActivityTypes,
  logActivity,
  removeActivity,
  setActivityTimes,
  startActivity,
} from "./api";
import { formatDuration, shortDate } from "./labels";

export const ACTIVITY_HUE = 6;

export function describeActivity(activity: Activity): string {
  return [
    activity.start_time?.slice(0, 5),
    activity.ongoing ? "en curso" : activity.duration_seconds ? formatDuration(activity.duration_seconds) : null,
    activity.band?.heart_rate_avg ? `${Math.round(activity.band.heart_rate_avg)} lpm` : null,
    activity.notes,
  ]
    .filter(Boolean)
    .join(" · ");
}

export const BAND_KINDS: { value: string; label: string }[] = [
  { value: "STATIONARY_BIKE", label: "Bici estática" },
  { value: "SPINNING", label: "Spinning" },
  { value: "BIKING", label: "Bici" },
  { value: "PADEL", label: "Pádel" },
  { value: "TENNIS", label: "Tenis" },
  { value: "RUNNING", label: "Correr" },
  { value: "TREADMILL", label: "Cinta" },
  { value: "ELLIPTICAL", label: "Elíptica" },
  { value: "ROWING_MACHINE", label: "Remo" },
  { value: "SWIMMING", label: "Natación" },
  { value: "HIIT", label: "HIIT" },
  { value: "YOGA", label: "Yoga" },
  { value: "CLIMBING", label: "Escalada" },
  { value: "HIKING", label: "Senderismo" },
  { value: "SOCCER", label: "Fútbol" },
];

export function nowMinute(now = new Date()): string {
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export function secondsBetween(start: string, end: string): number | null {
  if (!start || !end) return null;
  const minutes = (text: string) => Number(text.slice(0, 2)) * 60 + Number(text.slice(3, 5));
  let span = minutes(end) - minutes(start);
  if (span < 0) span += 24 * 60;
  return span * 60;
}

export function endOf(activity: Activity): string {
  const start = Number(activity.start_time.slice(0, 2)) * 60 + Number(activity.start_time.slice(3, 5));
  const end = (start + Math.round((activity.duration_seconds ?? 3600) / 60)) % (24 * 60);
  return `${String(Math.floor(end / 60)).padStart(2, "0")}:${String(end % 60).padStart(2, "0")}`;
}

function instant(day: string, clock: string, nextDay = false): string {
  const moment = new Date(`${day}T${clock.slice(0, 5)}:00`);
  if (nextDay) moment.setDate(moment.getDate() + 1);
  return moment.toISOString();
}

export function ActivityList({ activities, onOpen }: { activities: Activity[]; onOpen: (activity: Activity) => void }) {
  return (
    <List>
      {activities.map((activity) => (
        <ListRow
          key={activity.id}
          hue={ACTIVITY_HUE}
          title={activity.name}
          subtitle={[shortDate(activity.day), describeActivity(activity)].filter(Boolean).join(" · ")}
          accessory="chevron-right"
          onClick={() => onOpen(activity)}
        />
      ))}
    </List>
  );
}

export function ActivityQuick({
  types,
  ongoing,
  onChanged,
}: {
  types: ActivityType[];
  ongoing: Activity | null;
  onChanged: (activity: Activity) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(action: () => Promise<Activity>) {
    setBusy(true);
    setError(null);
    try {
      onChanged(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se ha podido guardar");
    } finally {
      setBusy(false);
    }
  }
  if (ongoing) {
    return (
      <Card title={ongoing.name}>
        <Inline>
          <Elapsed since={instant(ongoing.day, ongoing.start_time)} label={`desde las ${ongoing.start_time.slice(0, 5)}`} />
          <Button variant="secondary" size="small" icon="pause" disabled={busy} onClick={() => void run(() => finishActivity(ongoing.id))}>
            Terminar
          </Button>
        </Inline>
        {error && (
          <p className="training-field-error" role="alert">
            {error}
          </p>
        )}
      </Card>
    );
  }
  const shown = types.filter((type) => type.active).slice(0, 4);
  if (shown.length === 0) return null;
  return (
    <Inline label="Empezar una actividad">
      {shown.map((type) => (
        <Button
          key={type.id}
          variant="tinted"
          size="small"
          icon="play"
          disabled={busy}
          aria-label={`Empezar ${type.name}`}
          onClick={() => void run(() => startActivity(type.id))}
        >
          {type.name}
        </Button>
      ))}
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Inline>
  );
}

export interface LogActivitySheetProps {
  today: string;
  onClose: () => void;
  onLogged: (activity: Activity) => void;
}

export function nowQuarter(now = new Date()): string {
  const minutes = Math.floor(now.getMinutes() / 15) * 15;
  return `${String(now.getHours()).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function LogActivitySheet({ today, onClose, onLogged }: LogActivitySheetProps) {
  const [types, setTypes] = useState<ActivityType[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [day, setDay] = useState(today);
  const [start, setStart] = useState(() => nowMinute());
  const [end, setEnd] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listActivityTypes()
      .then((loaded) => setTypes(loaded.filter((type) => type.active)))
      .catch(() => setTypes([]));
  }, []);

  async function create() {
    if (!name.trim()) return;
    try {
      const type = await createActivityType(name.trim());
      setTypes((previous) => [...(previous ?? []).filter((t) => t.id !== type.id), type]);
      setChosen(type.id);
      setName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se ha podido crear");
    }
  }

  async function run(action: () => Promise<Activity>, failure: string) {
    if (!chosen || busy) return;
    setBusy(true);
    setError(null);
    try {
      onLogged(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : failure);
      setBusy(false);
    }
  }

  const save = () =>
    run(
      () =>
        logActivity({
          activity_type_id: chosen!,
          day,
          start_time: start,
          duration_seconds: secondsBetween(start, end),
          notes: notes.trim() || null,
        }),
      "No se ha podido anotar",
    );

  return (
    <Sheet
      title="Anotar actividad"
      onClose={onClose}
      action={{ label: busy ? "Anotando…" : "Anotar", onClick: () => void save(), disabled: !chosen || busy || !day || !start }}
    >
      <div className="training-field">
        <span className="training-field-label">Actividad</span>
        {types && types.length > 0 ? (
          <ChoiceChips
            label="Actividad"
            value={chosen ?? ""}
            onChange={setChosen}
            options={types.map((type) => ({ value: type.id, label: type.name }))}
          />
        ) : (
          <p className="training-field-hint">
            {types === null ? "Cargando…" : "Todavía no hay ninguna. Escribe la primera abajo."}
          </p>
        )}
      </div>
      <div className="training-inline-create">
        <TextField label="Nueva actividad" value={name} onChange={setName} placeholder="Escalada, pádel…" onSubmit={() => void create()} />
        <Button variant="tinted" size="small" icon="plus" disabled={!name.trim()} onClick={() => void create()}>
          Crear
        </Button>
      </div>
      <Button
        variant="primary"
        icon="play"
        disabled={!chosen || busy}
        onClick={() => void run(() => startActivity(chosen!), "No se ha podido empezar")}
      >
        Empezar ahora
      </Button>
      <p className="training-field-hint">O apunta cuándo fue, al minuto:</p>
      <div className="training-when">
        <DateField label="Día" value={day} max={today} onChange={setDay} />
        <TextField label="Desde" type="time" value={start} onChange={(next) => next && setStart(next)} />
        <TextField label="Hasta" type="time" value={end} onChange={setEnd} placeholder="Opcional" />
      </div>
      <TextField label="Nota" value={notes} onChange={setNotes} placeholder="Opcional" />
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}

export function bandLine(activity: Activity): string | null {
  const band = activity.band;
  if (!band) return null;
  const parts = [
    band.kcal != null ? `${Math.round(band.kcal)} kcal` : null,
    band.heart_rate_avg != null ? `media ${Math.round(band.heart_rate_avg)} lpm` : null,
    band.heart_rate_max != null ? `máx. ${Math.round(band.heart_rate_max)}` : null,
    band.active_zone_min ? `${Math.round(band.active_zone_min)} min en zona` : null,
    band.distance_km ? `${band.distance_km.toFixed(1).replace(".", ",")} km` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

export function ActivitySheet({
  activity,
  onClose,
  onRemoved,
  onChanged,
}: {
  activity: Activity;
  onClose: () => void;
  onRemoved: (id: string) => void;
  onChanged?: (activity: Activity) => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [start, setStart] = useState(activity.start_time.slice(0, 5));
  const [end, setEnd] = useState(activity.ongoing ? "" : endOf(activity));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const detail = describeActivity(activity);
  const measured = bandLine(activity);

  async function act(action: () => Promise<Activity>) {
    setBusy(true);
    setError(null);
    try {
      onChanged?.(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se ha podido guardar");
    } finally {
      setBusy(false);
    }
  }

  if (confirm) {
    return (
      <ConfirmDelete
        title="¿Borrar esta actividad?"
        subject={`${activity.name} · ${shortDate(activity.day)}`}
        action="Borrar actividad"
        onCancel={() => setConfirm(false)}
        onConfirm={() => removeActivity(activity.id).then(() => onRemoved(activity.id))}
      />
    );
  }
  const crosses = Boolean(end) && end < start;
  return (
    <Sheet title={activity.name} onClose={onClose}>
      <Hint>
        {shortDate(activity.day)}
        {detail ? ` · ${detail}` : ""}
      </Hint>
      {activity.ongoing ? (
        <>
          <Elapsed since={`${activity.day}T${activity.start_time}`} label="En curso" size="large" />
          <Button variant="primary" icon="pause" disabled={busy} onClick={() => void act(() => finishActivity(activity.id))}>
            Terminar
          </Button>
        </>
      ) : (
        <>
          {measured && <Hint>Pulsera: {measured}</Hint>}
          <WorkoutPulseCard id={`training:activity:${activity.id}`} start={`${activity.day}T${activity.start_time}`} />
          <div className="training-when">
            <TextField label="Desde" type="time" value={start} onChange={(next) => next && setStart(next)} />
            <TextField label="Hasta" type="time" value={end} onChange={(next) => next && setEnd(next)} />
          </div>
          <Button
            variant="secondary"
            size="small"
            disabled={busy || !end || (start === activity.start_time.slice(0, 5) && end === endOf(activity))}
            onClick={() =>
              void act(() =>
                setActivityTimes(activity.id, instant(activity.day, start), instant(activity.day, end, crosses)),
              )
            }
          >
            Guardar horas
          </Button>
        </>
      )}
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
      <Button variant="plain" icon="trash" onClick={() => setConfirm(true)}>
        Borrar
      </Button>
    </Sheet>
  );
}

export const todayIso = (now: Date) => isoDay(now);
