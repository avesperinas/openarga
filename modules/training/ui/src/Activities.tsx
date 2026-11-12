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
  type Locale,
  type Translate,
  useLocale,
  useT,
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
import { decimal, formatDuration, shortDate } from "./labels";

export const ACTIVITY_HUE = 6;

export function describeActivity(activity: Activity, t: Translate): string {
  return [
    activity.start_time?.slice(0, 5),
    activity.ongoing ? t("common.ongoing") : activity.duration_seconds ? formatDuration(activity.duration_seconds) : null,
    activity.band?.heart_rate_avg ? t("common.bpm", { value: Math.round(activity.band.heart_rate_avg) }) : null,
    activity.notes,
  ]
    .filter(Boolean)
    .join(" · ");
}

const BAND_KIND_VALUES = [
  "STATIONARY_BIKE",
  "SPINNING",
  "BIKING",
  "PADEL",
  "TENNIS",
  "RUNNING",
  "TREADMILL",
  "ELLIPTICAL",
  "ROWING_MACHINE",
  "SWIMMING",
  "HIIT",
  "YOGA",
  "CLIMBING",
  "HIKING",
  "SOCCER",
];

export const bandKinds = (t: Translate): { value: string; label: string }[] =>
  BAND_KIND_VALUES.map((value) => ({ value, label: t(`band_kind.${value}`) }));

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
  const t = useT();
  const locale = useLocale();
  return (
    <List>
      {activities.map((activity) => (
        <ListRow
          key={activity.id}
          hue={ACTIVITY_HUE}
          title={activity.name}
          subtitle={[shortDate(activity.day, locale), describeActivity(activity, t)].filter(Boolean).join(" · ")}
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
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(action: () => Promise<Activity>) {
    setBusy(true);
    setError(null);
    try {
      onChanged(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("common.save_failed"));
    } finally {
      setBusy(false);
    }
  }
  if (ongoing) {
    return (
      <Card title={ongoing.name}>
        <Inline>
          <Elapsed since={instant(ongoing.day, ongoing.start_time)} label={t("activity.since", { time: ongoing.start_time.slice(0, 5) })} />
          <Button variant="secondary" size="small" icon="pause" disabled={busy} onClick={() => void run(() => finishActivity(ongoing.id))}>
            {t("activity.finish")}
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
    <Inline label={t("activity.start_one")}>
      {shown.map((type) => (
        <Button
          key={type.id}
          variant="tinted"
          size="small"
          icon="play"
          disabled={busy}
          aria-label={t("activity.start_named", { name: type.name })}
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
  const t = useT();
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
      setTypes((previous) => [...(previous ?? []).filter((one) => one.id !== type.id), type]);
      setChosen(type.id);
      setName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("common.create_failed"));
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
      t("activity.log_failed"),
    );

  return (
    <Sheet
      title={t("activity.log_title")}
      onClose={onClose}
      action={{ label: busy ? t("activity.logging") : t("activity.log"), onClick: () => void save(), disabled: !chosen || busy || !day || !start }}
    >
      <div className="training-field">
        <span className="training-field-label">{t("activity.label")}</span>
        {types && types.length > 0 ? (
          <ChoiceChips
            label={t("activity.label")}
            value={chosen ?? ""}
            onChange={setChosen}
            options={types.map((type) => ({ value: type.id, label: type.name }))}
          />
        ) : (
          <p className="training-field-hint">
            {types === null ? t("common.loading") : t("activity.none_yet")}
          </p>
        )}
      </div>
      <div className="training-inline-create">
        <TextField label={t("activity.new")} value={name} onChange={setName} placeholder={t("activity.new_placeholder")} onSubmit={() => void create()} />
        <Button variant="tinted" size="small" icon="plus" disabled={!name.trim()} onClick={() => void create()}>
          {t("common.create")}
        </Button>
      </div>
      <Button
        variant="primary"
        icon="play"
        disabled={!chosen || busy}
        onClick={() => void run(() => startActivity(chosen!), t("activity.start_failed"))}
      >
        {t("activity.start_now")}
      </Button>
      <p className="training-field-hint">{t("activity.or_when")}</p>
      <div className="training-when">
        <DateField label={t("common.day")} value={day} max={today} onChange={setDay} />
        <TextField label={t("common.from")} type="time" value={start} onChange={(next) => next && setStart(next)} />
        <TextField label={t("common.until")} type="time" value={end} onChange={setEnd} placeholder={t("common.optional")} />
      </div>
      <TextField label={t("common.note")} value={notes} onChange={setNotes} placeholder={t("common.optional")} />
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}

export function bandLine(activity: Activity, t: Translate, locale: Locale): string | null {
  const band = activity.band;
  if (!band) return null;
  const parts = [
    band.kcal != null ? `${Math.round(band.kcal)} kcal` : null,
    band.heart_rate_avg != null ? t("band.average", { value: Math.round(band.heart_rate_avg) }) : null,
    band.heart_rate_max != null ? t("band.max", { value: Math.round(band.heart_rate_max) }) : null,
    band.active_zone_min ? t("band.zone", { value: Math.round(band.active_zone_min) }) : null,
    band.distance_km ? `${decimal(band.distance_km, 1, locale)} km` : null,
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
  const t = useT();
  const locale = useLocale();
  const [confirm, setConfirm] = useState(false);
  const [start, setStart] = useState(activity.start_time.slice(0, 5));
  const [end, setEnd] = useState(activity.ongoing ? "" : endOf(activity));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const detail = describeActivity(activity, t);
  const measured = bandLine(activity, t, locale);

  async function act(action: () => Promise<Activity>) {
    setBusy(true);
    setError(null);
    try {
      onChanged?.(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("common.save_failed"));
    } finally {
      setBusy(false);
    }
  }

  if (confirm) {
    return (
      <ConfirmDelete
        title={t("activity.delete_title")}
        subject={`${activity.name} · ${shortDate(activity.day, locale)}`}
        action={t("activity.delete")}
        onCancel={() => setConfirm(false)}
        onConfirm={() => removeActivity(activity.id).then(() => onRemoved(activity.id))}
      />
    );
  }
  const crosses = Boolean(end) && end < start;
  return (
    <Sheet title={activity.name} onClose={onClose}>
      <Hint>
        {shortDate(activity.day, locale)}
        {detail ? ` · ${detail}` : ""}
      </Hint>
      {activity.ongoing ? (
        <>
          <Elapsed since={`${activity.day}T${activity.start_time}`} label={t("common.ongoing_title")} size="large" />
          <Button variant="primary" icon="pause" disabled={busy} onClick={() => void act(() => finishActivity(activity.id))}>
            {t("activity.finish")}
          </Button>
        </>
      ) : (
        <>
          {measured && <Hint>{t("band.line", { measured })}</Hint>}
          <WorkoutPulseCard id={`training:activity:${activity.id}`} start={`${activity.day}T${activity.start_time}`} />
          <div className="training-when">
            <TextField label={t("common.from")} type="time" value={start} onChange={(next) => next && setStart(next)} />
            <TextField label={t("common.until")} type="time" value={end} onChange={(next) => next && setEnd(next)} />
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
            {t("activity.save_times")}
          </Button>
        </>
      )}
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
      <Button variant="plain" icon="trash" onClick={() => setConfirm(true)}>
        {t("common.delete")}
      </Button>
    </Sheet>
  );
}

export const todayIso = (now: Date) => isoDay(now);
