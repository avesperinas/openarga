import {
  Badge,
  Button,
  DateField,
  Heading,
  Icon,
  IconButton,
  Notice,
  RecurrencePicker,
  Switch,
  TextField,
  addDays,
  dayStart,
  fromRRule,
  toRRule,
} from "@openarga/ui";
import * as React from "react";

import {
  type Layer,
  type Occurrence,
  type Scope,
  VIEWER_TZ,
  cancelEvent,
  createEvent,
  hideSubscribed,
  updateEvent,
} from "./api";
import { type Form, changesOf, draftOf, formOf, moveStart, problemOf } from "./form";

export type Opened =
  | { kind: "new"; form: Form }
  | { kind: "existing"; occurrence: Occurrence };

export interface AskScope {
  (question: "edit" | "cancel", allowed: Scope[]): Promise<Scope | null>;
}

interface Props {
  opened: Opened;
  layers: Layer[];
  onClose: () => void;
  onDone: (message: string) => Promise<void> | void;
  askScope: AskScope;
  presentation: "panel" | "sheet";
  twin?: Occurrence | null;
}

const dayLong = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" });
const dayShort = new Intl.DateTimeFormat("es-ES", { weekday: "short", day: "numeric", month: "short" });
const clock = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function whenOf(occurrence: Occurrence): { day: string; time: string } {
  if (occurrence.all_day) {
    const first = dayStart(occurrence.start);
    const lastKey = addDays(occurrence.end, -1);
    if (lastKey === occurrence.start) return { day: cap(dayLong.format(first)), time: "Todo el día" };
    return {
      day: `${cap(dayShort.format(first))} – ${dayShort.format(dayStart(lastKey))}`,
      time: "Todo el día",
    };
  }
  const start = new Date(occurrence.start);
  const end = new Date(occurrence.end);
  if (start.toDateString() === end.toDateString()) {
    return { day: cap(dayLong.format(start)), time: `${clock.format(start)} – ${clock.format(end)}` };
  }
  return {
    day: `${cap(dayShort.format(start))}, ${clock.format(start)} – ${dayShort.format(end)}, ${clock.format(end)}`,
    time: "",
  };
}

function elsewhere(occurrence: Occurrence): string | null {
  if (occurrence.all_day || occurrence.tz === VIEWER_TZ) return null;
  const there = new Intl.DateTimeFormat("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: occurrence.tz,
  }).format(new Date(occurrence.start));
  return `${there} en ${occurrence.tz.replace(/_/g, " ")}`;
}

function mapLink(place: string): string {
  const apple = typeof navigator !== "undefined" && /iPhone|iPad|Macintosh/.test(navigator.userAgent);
  return apple
    ? `https://maps.apple.com/?q=${encodeURIComponent(place)}`
    : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place)}`;
}

export function EventPanel({ opened, layers, onClose, onDone, askScope, presentation, twin = null }: Props) {
  const [editing, setEditing] = React.useState(opened.kind === "new");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const key = opened.kind === "new" ? "new" : opened.occurrence.id;
  React.useEffect(() => {
    setEditing(opened.kind === "new");
    setError(null);
  }, [key, opened.kind]);

  const occurrence = opened.kind === "existing" ? opened.occurrence : null;
  const layer = layers.find((l) => l.id === (occurrence?.calendar_id ?? (opened.kind === "new" ? opened.form.calendarId : "")));
  const own = layer?.origin === "own";
  const series = !!occurrence?.original_start;

  const hide = async () => {
    if (!occurrence) return;
    setBusy(true);
    try {
      await hideSubscribed(occurrence.id);
      await onDone("Oculto");
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  const removeMine = async () => {
    if (!occurrence) return;
    setBusy(true);
    try {
      await cancelEvent(occurrence.event_id, "all", occurrence.original_start);
      await onDone(`Quitado de ${layer?.name ?? "tu capa"}`);
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!occurrence) return;
    const scope = series ? await askScope("cancel", ["this", "following", "all"]) : "all";
    if (!scope) return;
    setBusy(true);
    try {
      await cancelEvent(occurrence.event_id, scope, occurrence.original_start);
      await onDone(scope === "this" || !series ? "Evento cancelado" : "Serie cancelada");
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <Editor
        key={key}
        opened={opened}
        layers={layers}
        busy={busy}
        error={error}
        presentation={presentation}
        onCancel={() => (opened.kind === "new" ? onClose() : setEditing(false))}
        onSave={async (before, after) => {
          const problem = problemOf(after);
          if (problem) {
            setError(problem);
            return;
          }
          setBusy(true);
          setError(null);
          try {
            if (opened.kind === "new") {
              await createEvent(draftOf(after, VIEWER_TZ));
              await onDone("Evento creado");
              onClose();
              return;
            }
            const current = opened.occurrence;
            const changes = changesOf(before, after, current.tz);
            if (Object.keys(changes).length === 0) {
              setEditing(false);
              return;
            }
            let scope: Scope = "all";
            if (current.original_start) {
              const allowed: Scope[] = "rrule" in changes || "calendar_id" in changes ? ["following", "all"] : ["this", "following", "all"];
              const chosen = await askScope("edit", allowed);
              if (!chosen) return;
              scope = chosen;
            }
            await updateEvent(current.event_id, changes, scope, current.original_start);
            await onDone("Cambios guardados");
            onClose();
          } catch (failure) {
            setError(failure instanceof Error ? failure.message : String(failure));
          } finally {
            setBusy(false);
          }
        }}
      />
    );
  }

  if (!occurrence) return null;
  const when = whenOf(occurrence);
  const there = elsewhere(occurrence);

  return (
    <div className="cr-panel-body" data-presentation={presentation}>
      <header className="cr-panel-head">
        <span className="cr-panel-layer" data-tone={layer?.tone}>
          <span className="tone-dot" />
          {layer?.name ?? "Capa"}
          {layer?.origin === "subscription" && <Badge>Suscrita</Badge>}
          {layer?.origin === "app" && <Badge>App</Badge>}
        </span>
        <div className="cr-panel-actions">
          {own && <IconButton icon="edit" label="Editar" size="small" variant="plain" onClick={() => setEditing(true)} />}
          {presentation === "panel" && <IconButton icon="close" label="Cerrar" size="small" variant="plain" onClick={onClose} />}
        </div>
      </header>

      <Heading>{occurrence.title}</Heading>
      {twin && own && (
        <Notice
          tone="info"
          title={`También está en ${layers.find((one) => one.id === twin.calendar_id)?.name ?? "otra capa"}`}
          action={{ label: "Quitar el mío", onClick: () => void removeMine() }}
        >
          «{twin.title}», a la misma hora.
          {twin.href && (
            <>
              {" "}
              <a className="cr-link" href={twin.href}>
                Abrir el de su app
              </a>
            </>
          )}
        </Notice>
      )}

      <dl className="cr-facts">
        <div className="cr-fact">
          <dt>
            <Icon name="clock" label="Cuándo" />
          </dt>
          <dd>
            <span className="cr-fact-main">{when.day}</span>
            {when.time && <span className="cr-fact-detail">{when.time}</span>}
            {there && <span className="cr-fact-detail">{there}</span>}
          </dd>
        </div>
        {occurrence.repeat && (
          <div className="cr-fact">
            <dt>
              <Icon name="repeat" label="Se repite" />
            </dt>
            <dd>
              <span className="cr-fact-main">{cap(occurrence.repeat)}</span>
              {occurrence.moved && <span className="cr-fact-detail">Esta se ha movido de su sitio</span>}
            </dd>
          </div>
        )}
        {occurrence.location && (
          <div className="cr-fact">
            <dt>
              <Icon name="pin" label="Lugar" />
            </dt>
            <dd>
              <a className="cr-link" href={mapLink(occurrence.location)} target="_blank" rel="noreferrer">
                {occurrence.location}
              </a>
            </dd>
          </div>
        )}
        {occurrence.url && (
          <div className="cr-fact">
            <dt>
              <Icon name="link" label="Enlace" />
            </dt>
            <dd>
              <a className="cr-link" href={occurrence.url} target="_blank" rel="noreferrer">
                {occurrence.url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
              </a>
            </dd>
          </div>
        )}
        {occurrence.notes && (
          <div className="cr-fact">
            <dt>
              <Icon name="note" label="Notas" />
            </dt>
            <dd className="cr-notes">{occurrence.notes}</dd>
          </div>
        )}
      </dl>

      {error && <p className="cr-error" role="alert">{error}</p>}

      {layer?.origin === "subscription" && (
        <footer className="cr-panel-foot">
          <p className="cr-sheet-note">Lo trae la suscripción y se actualiza solo: no se edita, pero se puede quitar de la vista.</p>
          <Button variant="secondary" icon="eye-off" onClick={hide} disabled={busy}>
            Ocultar
          </Button>
        </footer>
      )}

      {layer?.origin === "app" && (
        <footer className="cr-panel-foot">
          <p className="cr-sheet-note">Lo pone {layer.name} y se actualiza solo: se cambia allí.</p>
          {occurrence.href && (
            <Button variant="secondary" icon="chevron-right" onClick={() => occurrence.href && window.location.assign(occurrence.href)}>
              Abrir en {layer.name}
            </Button>
          )}
        </footer>
      )}

      {own && (
        <footer className="cr-panel-foot">
          <Button variant="secondary" icon="edit" onClick={() => setEditing(true)} disabled={busy}>
            Editar
          </Button>
          <Button variant="plain" onClick={cancel} disabled={busy}>
            <span className="cr-danger">Cancelar evento</span>
          </Button>
        </footer>
      )}
    </div>
  );
}

interface EditorProps {
  opened: Opened;
  layers: Layer[];
  busy: boolean;
  error: string | null;
  presentation: "panel" | "sheet";
  onCancel: () => void;
  onSave: (before: Form, after: Form) => void;
}

function Editor({ opened, layers, busy, error, presentation, onCancel, onSave }: EditorProps) {
  const initial = React.useMemo(
    () => (opened.kind === "new" ? opened.form : formOf(opened.occurrence, opened.occurrence.rrule)),
    [],
  );
  const [form, setForm] = React.useState<Form>(initial);
  const set = <K extends keyof Form>(name: K, value: Form[K]) => setForm((current) => ({ ...current, [name]: value }));
  const own = layers.filter((l) => l.origin === "own");
  const titleRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (opened.kind === "new") titleRef.current?.focus();
  }, [opened.kind]);

  const save = () => onSave(initial, form);
  const rule = React.useMemo(() => {
    try {
      return form.rrule ? fromRRule(form.rrule) : null;
    } catch {
      return null;
    }
  }, [form.rrule]);

  return (
    <form
      className="cr-panel-body cr-editor"
      data-presentation={presentation}
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
          event.preventDefault();
          save();
        }
      }}
    >
      {presentation === "panel" && (
        <header className="cr-panel-head">
          <span className="cr-panel-kicker">{opened.kind === "new" ? "Nuevo evento" : "Editar"}</span>
          <div className="cr-panel-actions">
            <IconButton icon="close" label="Cerrar" size="small" variant="plain" onClick={onCancel} />
          </div>
        </header>
      )}

      <input
        ref={titleRef}
        className="cr-title-input"
        value={form.title}
        placeholder="Título"
        aria-label="Título"
        maxLength={200}
        enterKeyHint="done"
        onChange={(event) => set("title", event.target.value)}
      />

      <div className="cr-layers-pick" role="radiogroup" aria-label="Capa">
        {own.map((layer) => (
          <button
            key={layer.id}
            type="button"
            role="radio"
            aria-checked={form.calendarId === layer.id}
            className="cr-layer-chip"
            data-tone={layer.tone}
            onClick={() => set("calendarId", layer.id)}
          >
            <span className="tone-dot" />
            {layer.name}
          </button>
        ))}
      </div>

      <section className="cr-group">
        <div className="cr-switch-row">
          <span className="cr-switch-label" aria-hidden="true">
            Todo el día
          </span>
          <Switch label="Todo el día" checked={form.allDay} onChange={(value) => set("allDay", value)} />
        </div>
        <div className="cr-when">
          <div className="cr-when-row">
            <DateField
              label={form.allDay ? "Desde" : "Empieza"}
              value={form.startDay}
              onChange={(day) => day && setForm((f) => moveStart(f, day, f.startTime))}
            />
            {!form.allDay && (
              <input
                type="time"
                className="cr-input"
                aria-label="Hora de inicio"
                step={300}
                value={form.startTime}
                required
                onChange={(event) => event.target.value && setForm((f) => moveStart(f, f.startDay, event.target.value))}
              />
            )}
          </div>
          <div className="cr-when-row">
            <DateField
              label={form.allDay ? "Hasta" : "Acaba"}
              value={form.endDay}
              min={form.startDay}
              onChange={(day) => day && set("endDay", day)}
            />
            {!form.allDay && (
              <input
                type="time"
                className="cr-input"
                aria-label="Hora de fin"
                step={300}
                value={form.endTime}
                required
                onChange={(event) => event.target.value && set("endTime", event.target.value)}
              />
            )}
          </div>
        </div>
      </section>

      <section className="cr-group">
        <RecurrencePicker
          date={form.startDay}
          value={rule}
          onChange={(value) => set("rrule", value ? toRRule(value) : null)}
        />
      </section>

      <section className="cr-group">
        <TextField label="Lugar" value={form.location} placeholder="Dónde" onChange={(value) => set("location", value)} />
        <TextField label="Enlace" value={form.url} placeholder="https://" onChange={(value) => set("url", value)} />
        <label className="cr-textarea">
          <span className="cr-when-label">Notas</span>
          <textarea
            className="cr-input"
            rows={4}
            maxLength={8000}
            value={form.notes}
            onChange={(event) => set("notes", event.target.value)}
          />
        </label>
      </section>

      {error && <p className="cr-error" role="alert">{error}</p>}

      <footer className="cr-panel-foot">
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          Cancelar
        </Button>
        <Button variant="primary" type="submit" disabled={busy}>
          {busy ? "Guardando…" : opened.kind === "new" ? "Crear" : "Guardar"}
        </Button>
      </footer>
    </form>
  );
}
