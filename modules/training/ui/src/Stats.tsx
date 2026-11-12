import {
  BodyMaps,
  Button,
  Card,
  Figures,
  HeadlineFigure,
  Notice,
  Panes,
  Screen,
  Skeleton,
  Stack,
  ChoiceChips,
  EmptyState,
  GroupLabel,
  Hint,
  Section,
  Icon,
  ListRow,
  Sheet,
  Sparkline,
  TrendChart,
  changeColor,
  type Locale,
  type Translate,
  useLocale,
  useT,
} from "@openarga/ui";
import { peek, remember } from "@openarga/app";
import { type CSSProperties, useCallback, useEffect, useState } from "react";

import {
  type Machine,
  type MuscleStats,
  type MuscleSummary,
  type Period,
  type Stats,
  type VariantPoint,
  type VariantStats,
  addMark,
  clearPoint,
  judgePoint,
  readMuscleStats,
  readStats,
  readVariantStats,
  removeMark,
} from "./api";
import { AppVersion } from "./AppVersion";
import { ScreenHeader } from "./Header";
import { advice, normalRange, recordIds } from "./exercise";
import { amount, decimal, longDate, muscleName, plural, regions } from "./labels";
import { shortDay } from "./prefill";

const PERIODS: Period[] = ["4w", "3m", "1y", "all"];

const statsKey = (period: Period) => `stats:${period}`;

export function periodLabel(period: Period, t: Translate): string {
  return t(`stats.period.${period}`);
}

export function signed(value: number, locale: Locale): string {
  return `${value >= 0 ? "+" : "−"}${decimal(Math.abs(value), 1, locale)} %`;
}

const kg = (value: number, locale: Locale) =>
  `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)} kg`;

const tenths = (value: number, locale: Locale) => decimal(value, 1, locale);

export function sparkline(values: number[], width = 320, height = 64): string {
  if (values.length < 2) return "";
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - 6 - ((value - low) / span) * (height - 12);
      return `${Math.round(x * 10) / 10},${Math.round(y * 10) / 10}`;
    })
    .join(" ");
}

export function exerciseLabel(entry: { exercise: string; variant: string }): string {
  return entry.variant.toLowerCase().includes(entry.exercise.toLowerCase())
    ? entry.variant
    : `${entry.exercise} · ${entry.variant}`;
}

export function whyNot(point: VariantPoint, t: Translate, locale: Locale): string | null {
  if (point.status === "excluded") return t("stats.why.excluded");
  if (point.status === "counted") return point.verdict === "counted" ? t("stats.why.counted") : null;
  const reference = point.reference ? t("stats.why.usual", { load: kg(point.reference, locale) }) : "";
  const gap = point.reference ? Math.round(Math.abs(point.e1rm / point.reference - 1) * 100) : null;
  return t(point.status === "high" ? "stats.why.above" : "stats.why.below", { gap: gap ?? "?", reference }).trim();
}

type Detail =
  | { kind: "muscle"; id: string }
  | { kind: "variant"; id: string; gym: string | null }
  | { kind: "point"; variant: VariantStats; machine: Machine; point: VariantPoint };

export function StatsScreen({
  onOpenSession,
  initial,
}: {
  onOpenSession?: (id: string) => void;
  initial?: Stats;
}) {
  const t = useT();
  const [period, setPeriod] = useState<Period>("3m");
  const [stats, setStats] = useState<Stats | null>(() => initial ?? peek<Stats>(statsKey("3m")) ?? null);
  const [failed, setFailed] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [stack, setStack] = useState<Detail[]>(() => {
    if (typeof window === "undefined") return [];
    const variant = new URLSearchParams(window.location.search).get("variant");
    return variant ? [{ kind: "variant", id: variant, gym: null }] : [];
  });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (initial && period === initial.period && version === 0) return;
    let current = true;
    setFailed(false);
    const kept = peek<Stats>(statsKey(period));
    if (kept) setStats(kept);
    readStats(period)
      .then((body) => {
        remember(statsKey(period), body);
        if (current) setStats(body);
      })
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [period, version, initial]);

  const open = (detail: Detail) => setStack((previous) => [...previous, detail]);
  const back = () => setStack((previous) => previous.slice(0, -1));
  const changed = () => {
    setVersion((value) => value + 1);
    back();
  };
  const top = stack[stack.length - 1];

  return (
    <Screen wide>
      <ScreenHeader title={t("tabs.stats")} />

      <button type="button" className="training-period" onClick={() => setChoosing(true)}>
        {periodLabel(period, t)}
        <span aria-hidden="true">▾</span>
      </button>

      {failed ? (
        <EmptyState title={t("stats.load_failed")}>{t("stats.load_failed_hint")}</EmptyState>
      ) : !stats ? (
        <Skeleton rows={4} label={t("stats.loading")} />
      ) : stats.sessions === 0 ? (
        <EmptyState title={t("stats.empty")}>{t("stats.empty_hint")}</EmptyState>
      ) : (
        <Panes
          asideLabel={t("stats.aside")}
          main={
            <>
              <VolumeCard stats={stats} onOpen={(id) => open({ kind: "muscle", id })} />
              <IndexCard stats={stats} />
            </>
          }
          aside={
            <>
              <FrequencyCards stats={stats} />
              <MoversCard stats={stats} onOpen={(id, gym) => open({ kind: "variant", id, gym })} />
            </>
          }
        />
      )}

      <AppVersion />

      {choosing && (
        <Sheet title={t("stats.period")} onClose={() => setChoosing(false)}>
          <ul className="training-period-list">
            {PERIODS.map((entry) => (
              <li key={entry}>
                <button
                  type="button"
                  className="training-period-option"
                  aria-current={entry === period || undefined}
                  onClick={() => {
                    setPeriod(entry);
                    setChoosing(false);
                  }}
                >
                  {periodLabel(entry, t)}
                  {entry === "all" && stats ? (
                    <span className="training-period-count">{plural(t, "stats.workouts", stats.sessions)}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </Sheet>
      )}

      {top?.kind === "muscle" && (
        <MuscleSheet
          key={top.id}
          muscle={top.id}
          period={period}
          onClose={back}
          onOpen={(id) => open({ kind: "variant", id, gym: null })}
        />
      )}
      {top?.kind === "variant" && (
        <VariantSheet
          key={top.id}
          variantId={top.id}
          gym={top.gym}
          period={period}
          onClose={back}
          onChanged={() => setVersion((value) => value + 1)}
          onPoint={(variant, machine, point) =>
            setStack((previous) => [
              ...previous.slice(0, -1),
              { kind: "variant", id: variant.variant_id, gym: machine.gym_id ?? "-" },
              { kind: "point", variant, machine, point },
            ])
          }
        />
      )}
      {top?.kind === "point" && (
        <PointSheet
          variant={top.variant}
          machine={top.machine}
          point={top.point}
          onClose={back}
          onDone={changed}
          onOpenSession={onOpenSession}
        />
      )}
    </Screen>
  );
}

function IndexCard({ stats }: { stats: Stats }) {
  const t = useT();
  const locale = useLocale();
  const { index } = stats;
  if (index.value === null || index.delta === null) {
    return (
      <Section title={t("stats.performance")}>
        <div className="surface training-card">
          <Hint>{t("stats.index_missing")}</Hint>
        </div>
      </Section>
    );
  }
  const values = index.trend.map((point) => point.value);
  return (
    <Section title={t("stats.performance")}>
      <Card label={t("stats.index")}>
        <div className="training-card-head">
          <div className="training-index-figure">
            <p className="training-index-value">
              {tenths(index.value, locale)}
              <span className="training-index-delta" data-direction={index.direction ?? "flat"}>
                {signed(index.delta, locale)}
              </span>
            </p>
          </div>
          <span className="training-light" data-direction={index.direction ?? "flat"}>
            {t(`stats.light.${index.direction ?? "flat"}`)}
          </span>
        </div>
        {values.length > 1 && <Sparkline series={values} label={t("stats.index_trend")} />}
        <p className="training-card-note">
          {plural(t, "stats.index_note", index.muscles)}
          {stats.excluded > 0 ? ` · ${plural(t, "stats.set_aside", stats.excluded)}` : ""}
        </p>
      </Card>
    </Section>
  );
}

function FrequencyCards({ stats }: { stats: Stats }) {
  const t = useT();
  const locale = useLocale();
  const { frequency } = stats;
  const met = frequency.goal > 0 && frequency.done >= frequency.goal;
  const average = t("stats.average_4w", { value: tenths(frequency.average, locale) });
  return (
    <Section title={t("stats.consistency")}>
      <div className="training-stat-pair">
        <section className="surface training-card" data-done={met || undefined}>
          <h3 className="training-card-title">{t("today.this_week")}</h3>
          <p className="training-stat-figure">
            {frequency.done} <span className="training-stat-unit">{t("stats.of_goal", { goal: frequency.goal })}</span>
            {met && (
              <span className="training-stat-done">
                <Icon name="done" label={t("stats.goal_met")} />
              </span>
            )}
          </p>
          <p className="training-card-note">{met ? `${t("stats.goal_met_lower")} · ${average}` : average}</p>
        </section>
        <section className="surface training-card">
          <h3 className="training-card-title">{t("stats.streak")}</h3>
          <p className="training-stat-figure">
            {frequency.streak} <span className="training-stat-unit">{t("stats.weeks_short")}</span>
          </p>
          <p className="training-card-note">
            {frequency.streak === 0 ? t("stats.no_weeks_met") : t("stats.meeting_goal")}
          </p>
        </section>
      </div>
    </Section>
  );
}

export function VolumeCard({ stats, onOpen }: { stats: Stats; onOpen: (muscle: string) => void }) {
  const t = useT();
  const most = Math.max(...stats.muscles.map((entry) => entry.sets), 20);
  return (
    <Section title={t("muscles.label")}>
      <div className="surface training-card" aria-label={t("muscles.label")}>
        <BodyMaps
          label={t("stats.strength_by_muscle")}
          colors={Object.fromEntries(stats.muscles.map((entry) => [entry.muscle, changeColor(entry.delta)]))}
          names={Object.fromEntries(
            stats.muscles.map((entry) => [entry.muscle, muscleName(t, { id: entry.muscle, name: entry.name })]),
          )}
          onSelect={onOpen}
        />
        <p className="training-card-note">{t("stats.colours")}</p>
        <Hint>{t("stats.per_muscle")}</Hint>
        {regions(t).map((region) => {
          const muscles = stats.muscles.filter((entry) => entry.region === region.value);
          if (muscles.length === 0) return null;
          return (
            <div key={region.value} className="training-muscle-group">
              <span className="training-card-note">{region.label}</span>
              <ul className="training-volume">
                {muscles.map((entry) => (
                  <MuscleRow key={entry.muscle} entry={entry} most={most} onOpen={onOpen} />
                ))}
              </ul>
            </div>
          );
        })}
        {stats.bodyweight === null && (
          <p className="training-card-note">{t("stats.no_bodyweight")}</p>
        )}
      </div>
    </Section>
  );
}

function MuscleRow({
  entry,
  most,
  onOpen,
}: {
  entry: MuscleSummary;
  most: number;
  onOpen: (muscle: string) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const name = muscleName(t, { id: entry.muscle, name: entry.name });
  return (
    <li>
      <button
        type="button"
        className="training-volume-row training-pressable"
        aria-label={t("stats.muscle_row", {
          name,
          strength: entry.delta === null ? t("stats.no_strength") : t("stats.strength", { delta: signed(entry.delta, locale) }),
          sets: tenths(entry.sets, locale),
        })}
        onClick={() => onOpen(entry.muscle)}
      >
        <span className="training-volume-name">{name}</span>
        <span
          className="training-volume-delta"
          data-direction={entry.direction ?? undefined}
        >
          {entry.delta === null ? "—" : signed(entry.delta, locale)}
        </span>
        <span className="training-volume-track">
          <span
            className="training-volume-fill"
            data-band={entry.band}
            style={{ "--fill-to": `${Math.min((entry.sets / most) * 100, 100)}%` } as CSSProperties}
          />
        </span>
        <span className="training-volume-value">{tenths(entry.sets, locale)}</span>
      </button>
    </li>
  );
}

function MoversCard({ stats, onOpen }: { stats: Stats; onOpen: (id: string, gym: string | null) => void }) {
  const t = useT();
  const locale = useLocale();
  const shown = [...stats.movers.slice(0, 3), ...stats.movers.slice(-2)].filter(
    (mover, index, all) =>
      all.findIndex((other) => other.variant_id === mover.variant_id && other.gym_id === mover.gym_id) === index,
  );
  if (shown.length === 0) return null;
  return (
    <Section title={t("stats.movers")}>
      <div className="surface training-card">
        <ul className="training-movers">
          {shown.map((mover) => (
            <li key={`${mover.variant_id}:${mover.gym_id ?? "-"}`}>
              <button type="button" className="training-mover" onClick={() => onOpen(mover.variant_id, mover.gym_id)}>
                <span className="training-mover-text">
                  <span className="training-mover-name">{exerciseLabel(mover)}</span>
                  <span className="training-card-note">
                    {mover.gym ? `${mover.gym} · ` : ""}e1RM {kg(mover.e1rm, locale)}
                    {mover.without_pr >= 3 ? ` · ${t("stats.without_pr", { count: mover.without_pr })}` : ""}
                  </span>
                </span>
                <span className="training-mover-delta" data-direction={mover.delta >= 0 ? "up" : "down"}>
                  {signed(mover.delta, locale)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

function useLoad<T>(load: () => Promise<T>): { data: T | null; failed: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setFailed(false);
    load()
      .then((body) => current && setData(body))
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [load, attempt]);
  return { data, failed, reload: () => setAttempt((value) => value + 1) };
}

function since(day: string | null, t: Translate, locale: Locale): string {
  if (!day) return t("stats.never");
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  const days = Math.round((Date.now() - new Date(year, month - 1, date).getTime()) / 86_400_000);
  if (days <= 0) return t("stats.today");
  if (days === 1) return t("stats.yesterday");
  if (days < 30) return t("stats.days_ago", { count: days });
  return shortDay(day, locale);
}

function month(day: string, locale: Locale): string {
  const [year = 1970, value = 1] = day.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { month: "short", year: "numeric" })
    .format(new Date(year, value - 1, 1))
    .replace(".", "");
}

function MuscleSheet({
  muscle,
  period,
  onClose,
  onOpen,
}: {
  muscle: string;
  period: Period;
  onClose: () => void;
  onOpen: (variantId: string) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const load = useCallback(() => readMuscleStats(muscle, period), [muscle, period]);
  const { data: detail, failed } = useLoad<MuscleStats>(load);

  return (
    <Sheet title={detail ? muscleName(t, { id: muscle, name: detail.name }) : t("stats.muscle")} onClose={onClose}>
      {failed ? (
        <p className="training-field-error" role="alert">
          {t("stats.muscle_failed")}
        </p>
      ) : !detail ? (
        <Hint>{t("common.loading")}</Hint>
      ) : (
        <>
          {detail.value !== null && detail.delta !== null ? (
            <p className="training-index-value">
              {tenths(detail.value, locale)}
              <span className="training-index-delta" data-direction={detail.direction ?? "flat"}>
                {signed(detail.delta, locale)}
              </span>
            </p>
          ) : (
            <Hint>{t("stats.not_enough")}</Hint>
          )}
          {detail.trend.length > 1 && (
            <MarkedSpark
              values={detail.trend.map((point) => point.value)}
              days={detail.trend.map((point) => point.day)}
              marks={detail.changes}
              label={t("stats.strength_of", { name: muscleName(t, { id: muscle, name: detail.name }).toLowerCase() })}
            />
          )}
          <p className="training-card-note">
            {t("stats.muscle_note", { sets: tenths(detail.sets, locale), last: since(detail.last_day, t, locale) })}
            {detail.changes.length > 0 ? ` · ${t("stats.lines_are_changes")}` : ""}
          </p>

          <h3 className="training-card-title">{t("stats.exercises_all_time")}</h3>
          {detail.exercises.length === 0 ? (
            <Hint>{t("stats.no_primary")}</Hint>
          ) : (
            <ul className="training-movers">
              {detail.exercises.map((exercise) => (
                <li key={exercise.variant_id}>
                  <button type="button" className="training-mover" onClick={() => onOpen(exercise.variant_id)}>
                    <span className="training-mover-text">
                      <span className="training-mover-name">{exerciseLabel(exercise)}</span>
                      <span className="training-card-note">
                        {exercise.gyms.join(", ")} · {month(exercise.first_day, locale)} –{" "}
                        {since(exercise.last_day, t, locale)} · {plural(t, "stats.sessions", exercise.sessions)}
                        {exercise.excluded > 0 ? ` · ${t("stats.excluded", { count: exercise.excluded })}` : ""}
                      </span>
                    </span>
                    {exercise.delta !== null ? (
                      <span className="training-mover-delta" data-direction={exercise.delta >= 0 ? "up" : "down"}>
                        {signed(exercise.delta, locale)}
                      </span>
                    ) : exercise.last !== null ? (
                      <span className="training-mover-delta">{kg(exercise.last, locale)}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button variant="secondary" block onClick={onClose}>
            {t("common.close")}
          </Button>
        </>
      )}
    </Sheet>
  );
}

function MarkedSpark({ values, days, marks, label }: { values: number[]; days: string[]; marks: string[]; label: string }) {
  const at = (day: string) => {
    const index = days.findIndex((candidate, position) => candidate <= day && (days[position + 1] ?? "9999") > day);
    return index < 0 ? null : (index / Math.max(days.length - 1, 1)) * 320;
  };
  return (
    <svg className="training-spark" viewBox="0 0 320 64" role="img" aria-label={label}>
      {marks.map((day) => {
        const x = at(day);
        return x === null ? null : <line key={day} className="training-spark-mark" x1={x} x2={x} y1={0} y2={64} />;
      })}
      <polyline points={sparkline(values)} fill="none" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const LIMIT = 20;

function VariantSheet({
  variantId,
  gym,
  period,
  onClose,
  onChanged,
  onPoint,
}: {
  variantId: string;
  gym: string | null;
  period: Period;
  onClose: () => void;
  onChanged: () => void;
  onPoint: (variant: VariantStats, machine: Machine, point: VariantPoint) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const load = useCallback(() => readVariantStats(variantId, period), [variantId, period]);
  const { data: detail, failed, reload } = useLoad<VariantStats>(load);
  const [chosen, setChosen] = useState<string | null>(gym);
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const key = (machine: Machine) => machine.gym_id ?? "-";
  const machine = detail?.machines.find((candidate) => key(candidate) === chosen) ?? detail?.machines[0];

  async function act(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      reload();
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("common.save_failed"));
    }
  }

  const bodyweight = detail?.load_type !== "external";
  return (
    <Sheet title={detail ? exerciseLabel(detail) : t("session.variant")} onClose={onClose}>
      {failed ? (
        <p className="training-field-error" role="alert">
          {t("stats.variant_failed")}
        </p>
      ) : !detail ? (
        <Hint>{t("common.loading")}</Hint>
      ) : !machine ? (
        <Hint>
          {bodyweight && detail.bodyweight === null
            ? t("stats.log_bodyweight")
            : t("stats.no_counted_session")}
        </Hint>
      ) : (
        <>
          {detail.machines.length > 1 && (
            <ChoiceChips
              label={t("stats.gym")}
              value={key(machine)}
              onChange={(value) => {
                setChosen(value);
                setAll(false);
              }}
              options={detail.machines.map((candidate) => ({
                value: key(candidate),
                label: candidate.gym ?? t("stats.no_gym"),
              }))}
            />
          )}
          <Hint>
            {detail.machines.length > 1
              ? t("stats.gyms_differ")
              : machine.gym ?? t("stats.no_gym")}
            {" · "}
            {t("stats.step", { step: tenths(detail.min_increment, locale) })}
            {bodyweight ? ` · ${t("stats.bodyweight_load")}` : ""}
          </Hint>

          <ExerciseSummary machine={machine} increment={detail.min_increment} external={!bodyweight} period={period} />

          <Changes
            machine={machine}
            onJoin={(day) =>
              void act(() => addMark({ variant_id: variantId, gym_id: machine.gym_id, day, kind: "join" }))
            }
            onRemove={(id) => void act(() => removeMark(id))}
          />

          <h3 className="training-card-title">
            {t("stats.sessions_title")}
            {machine.excluded > 0 ? ` · ${t("stats.not_counting", { count: machine.excluded })}` : ""}
          </h3>
          <p className="training-card-note">{t("stats.outlier_rule")}</p>
          <ul className="training-movers">
            {[...machine.points]
              .reverse()
              .filter((point, index) => all || point.status !== "counted" || index < LIMIT)
              .map((point) => (
                <li key={point.id}>
                  <button
                    type="button"
                    className="training-mover"
                    data-status={point.status}
                    onClick={() => onPoint(detail, machine, point)}
                  >
                    <span className="training-mover-text">
                      <span className="training-mover-name">
                        {shortDay(point.day, locale)} · {point.reps} × {kg(point.load, locale)}
                      </span>
                      {whyNot(point, t, locale) && <span className="training-card-note">{whyNot(point, t, locale)}</span>}
                    </span>
                    <span className="training-point-e1rm" data-status={point.status}>
                      {kg(point.e1rm, locale)}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
          {!all && machine.points.filter((point) => point.status === "counted").length > LIMIT && (
            <Button variant="plain" size="small" onClick={() => setAll(true)}>
              {t("stats.see_all")}
            </Button>
          )}

          {error && (
            <p className="training-field-error" role="alert">
              {error}
            </p>
          )}
          <Button variant="secondary" block onClick={onClose}>
            {t("common.close")}
          </Button>
        </>
      )}
      {detail && detail.notes.length > 0 && (
        <section aria-label={t("stats.notes_mentioning")}>
          <GroupLabel count={detail.notes.length}>{t("stats.notes")}</GroupLabel>
          {detail.notes.map((note) => (
            <ListRow key={note.href} title={note.title} subtitle={note.line || undefined} onClick={() => window.location.assign(note.href)} />
          ))}
        </section>
      )}
    </Sheet>
  );
}

export function ExerciseSummary({
  machine,
  increment,
  external,
  period,
}: {
  machine: Machine;
  increment: number;
  external: boolean;
  period: Period;
}) {
  const t = useT();
  const locale = useLocale();
  const counted = machine.points.filter((point) => point.status === "counted");
  const first = counted[0];
  const last = counted[counted.length - 1];
  const records = recordIds(machine.points);
  const change = first && last && counted.length > 1 ? last.e1rm - first.e1rm : null;
  const said = advice(machine, increment, external, t, locale);
  return (
    <>
      {machine.best && (
        <Card label={t("stats.estimated_max")}>
          <HeadlineFigure
            label={t("stats.estimated_max")}
            value={amount(Math.round(machine.best.e1rm), locale)}
            unit="kg"
            change={
              change === null
                ? undefined
                : {
                    text: t("stats.change_in", {
                      change: `${change > 0 ? "+" : change < 0 ? "−" : "±"}${amount(Math.abs(Math.round(change * 10) / 10), locale)}`,
                      period: periodLabel(period, t).toLowerCase(),
                    }),
                    direction: change > 0 ? "up" : change < 0 ? "down" : "flat",
                  }
            }
          />
          {counted.length > 1 && (
            <TrendChart
              label={t("stats.estimated_max_per_session")}
              valueName={t("stats.estimated_max")}
              bandName={t("stats.normal_range")}
              highlightName={t("session.record")}
              flagOutside={false}
              format={(value) => `${amount(Math.round(value), locale)} kg`}
              band={normalRange(machine.points)}
              points={counted.map((point) => ({ day: point.day, value: point.e1rm, highlight: records.has(point.id) }))}
            />
          )}
        </Card>
      )}

      {said.length > 0 && (
        <Notice title={t("stats.what_it_says")}>
          {said.map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </Notice>
      )}

      {machine.records.length > 0 && (
        <Stack>
          <GroupLabel>{t("stats.records_by_reps")}</GroupLabel>
          <Card>
            <Figures
              items={machine.records.map((record) => ({
                label: `${record.range} reps`,
                value: `${amount(record.load, locale)} kg`,
                muted: !record.reliable,
              }))}
            />
          </Card>
          {machine.records.some((record) => !record.reliable) && (
            <Hint>{t("stats.grey_unreliable")}</Hint>
          )}
        </Stack>
      )}
    </>
  );
}

function Changes({
  machine,
  onJoin,
  onRemove,
}: {
  machine: Machine;
  onJoin: (day: string) => void;
  onRemove: (id: string) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const changes = machine.segments.slice(1);
  const joins = machine.marks.filter((mark) => mark.kind === "join");
  if (changes.length === 0 && joins.length === 0) return null;
  return (
    <ul className="training-movers">
      {changes.map((segment) => (
        <li key={segment.since} className="training-change">
          <span className="training-mover-text">
            <span className="training-mover-name">{t("stats.other_machine_since", { day: longDate(segment.since, locale) })}</span>
            <span className="training-card-note">
              {segment.start === "mark"
                ? t("stats.you_marked")
                : t("stats.detected", { jump: segment.jump === null ? t("stats.suddenly") : signed(segment.jump, locale) })}
            </span>
          </span>
          {segment.start === "mark" && segment.mark_id ? (
            <Button variant="plain" size="small" onClick={() => onRemove(segment.mark_id!)}>
              {t("plan.remove")}
            </Button>
          ) : segment.start === "detected" ? (
            <Button variant="plain" size="small" onClick={() => onJoin(segment.since)}>
              {t("stats.did_not_change")}
            </Button>
          ) : null}
        </li>
      ))}
      {joins.map((mark) => (
        <li key={mark.id} className="training-change">
          <span className="training-mover-text">
            <span className="training-mover-name">{t("stats.same_machine_on", { day: longDate(mark.day, locale) })}</span>
            <span className="training-card-note">{t("stats.you_said_same")}</span>
          </span>
          <Button variant="plain" size="small" onClick={() => onRemove(mark.id)}>
            {t("stats.undo")}
          </Button>
        </li>
      ))}
    </ul>
  );
}

function PointSheet({
  variant,
  machine,
  point,
  onClose,
  onDone,
  onOpenSession,
}: {
  variant: VariantStats;
  machine: Machine;
  point: VariantPoint;
  onClose: () => void;
  onDone: () => void;
  onOpenSession?: (id: string) => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("common.save_failed"));
      setBusy(false);
    }
  }

  const first = machine.segments.some((segment) => segment.since === point.day);
  return (
    <Sheet title={longDate(point.day, locale)} onClose={onClose}>
      <p className="training-index-value">
        {point.reps} × {kg(point.load, locale)}
        <span className="training-stat-unit"> · e1RM {kg(point.e1rm, locale)}</span>
      </p>
      <Hint>
        {exerciseLabel(variant)}
        {machine.gym ? ` · ${machine.gym}` : ""}
        {variant.load_type !== "external" ? ` · ${t("stats.bodyweight_load")}` : ""}
      </Hint>
      <p className={point.status === "counted" ? "training-card-note" : "training-warning"}>
        {whyNot(point, t, locale) ?? t("stats.counts")}
      </p>

      <div className="training-sheet-actions">
        {point.verdict !== null ? (
          <Button variant="secondary" block disabled={busy} onClick={() => void act(() => clearPoint(point.id))}>
            {t("stats.back_to_automatic")}
          </Button>
        ) : point.status === "counted" ? (
          <Button variant="secondary" block disabled={busy} onClick={() => void act(() => judgePoint(point.id, "excluded"))}>
            {t("stats.set_aside_day")}
          </Button>
        ) : (
          <Button variant="secondary" block disabled={busy} onClick={() => void act(() => judgePoint(point.id, "counted"))}>
            {t("stats.it_is_right")}
          </Button>
        )}
        {!first && (
          <Button
            variant="plain"
            block
            disabled={busy}
            onClick={() =>
              void act(() =>
                addMark({ variant_id: variant.variant_id, gym_id: machine.gym_id, day: point.day, kind: "split" }),
              )
            }
          >
            {t("stats.machine_changed")}
          </Button>
        )}
        {onOpenSession && (
          <Button variant="plain" block disabled={busy} onClick={() => onOpenSession(point.session_id)}>
            {t("stats.open_session")}
          </Button>
        )}
      </div>
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}
