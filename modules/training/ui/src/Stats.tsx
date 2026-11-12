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
  formatDecimal,
  Icon,
  ListRow,
  Sheet,
  Sparkline,
  TrendChart,
  changeColor,
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
import { REGIONS, longDate } from "./labels";
import { shortDay } from "./prefill";

const PERIODS: { id: Period; label: string }[] = [
  { id: "4w", label: "4 semanas" },
  { id: "3m", label: "3 meses" },
  { id: "1y", label: "Un año" },
  { id: "all", label: "Desde el principio" },
];

const statsKey = (period: Period) => `stats:${period}`;

const LIGHT: Record<string, string> = { up: "Mejorando", flat: "Estable", down: "Perdiendo" };

export function periodLabel(period: Period): string {
  return PERIODS.find((entry) => entry.id === period)?.label ?? "";
}

export function signed(value: number): string {
  const rounded = Math.abs(value).toFixed(1).replace(".", ",");
  return `${value >= 0 ? "+" : "−"}${rounded} %`;
}

const kg = (value: number) => `${value.toFixed(1).replace(".", ",").replace(/,0$/, "")} kg`;

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
  return entry.variant.toLowerCase().startsWith(entry.exercise.toLowerCase())
    ? entry.variant
    : `${entry.exercise} · ${entry.variant}`;
}

export function whyNot(point: VariantPoint): string | null {
  if (point.status === "excluded") return "Lo apartaste tú";
  if (point.status === "counted") return point.verdict === "counted" ? "Cuenta porque lo dijiste tú" : null;
  const reference = point.reference ? ` (lo habitual, ${kg(point.reference)})` : "";
  const gap = point.reference ? Math.round(Math.abs(point.e1rm / point.reference - 1) * 100) : null;
  const how = point.status === "high" ? "por encima" : "por debajo";
  return `Un ${gap ?? "?"} % ${how} de las sesiones de alrededor en esta máquina${reference}`;
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
  const [period, setPeriod] = useState<Period>("3m");
  const [stats, setStats] = useState<Stats | null>(() => initial ?? peek<Stats>(statsKey("3m")) ?? null);
  const [failed, setFailed] = useState(false);
  const [choosing, setChoosing] = useState(false);
  const [stack, setStack] = useState<Detail[]>(() => {
    if (typeof window === "undefined") return [];
    const variant = new URLSearchParams(window.location.search).get("variante");
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
      <ScreenHeader title="Stats" />

      <button type="button" className="training-period" onClick={() => setChoosing(true)}>
        {periodLabel(period)}
        <span aria-hidden="true">▾</span>
      </button>

      {failed ? (
        <EmptyState title={"No se han podido cargar tus stats"}>Comprueba la conexión y vuelve a abrir la pestaña.</EmptyState>
      ) : !stats ? (
        <Skeleton rows={4} label="Cargando tus stats" />
      ) : stats.sessions === 0 ? (
        <EmptyState title={"Todavía no hay nada que medir"}>En cuanto termines un entreno, esta pantalla empieza a contar.</EmptyState>
      ) : (
        <Panes
          asideLabel="Frecuencia y ejercicios"
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
        <Sheet title="Periodo" onClose={() => setChoosing(false)}>
          <ul className="training-period-list">
            {PERIODS.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  className="training-period-option"
                  aria-current={entry.id === period || undefined}
                  onClick={() => {
                    setPeriod(entry.id);
                    setChoosing(false);
                  }}
                >
                  {entry.label}
                  {entry.id === "all" && stats ? (
                    <span className="training-period-count">{stats.sessions} entrenos</span>
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
  const { index } = stats;
  if (index.value === null || index.delta === null) {
    return (
      <Section title="Rendimiento">
        <div className="surface training-card">
          <Hint>
            Hace falta que algún músculo tenga sesiones en al menos dos semanas del periodo. Con otro
            periodo más ancho, o unas semanas más, aparece.
          </Hint>
        </div>
      </Section>
    );
  }
  const values = index.trend.map((point) => point.value);
  return (
    <Section title="Rendimiento">
      <Card label="Índice de rendimiento">
        <div className="training-card-head">
          <div className="training-index-figure">
            <p className="training-index-value">
              {index.value.toFixed(1).replace(".", ",")}
              <span className="training-index-delta" data-direction={index.direction ?? "flat"}>
                {signed(index.delta)}
              </span>
            </p>
          </div>
          <span className="training-light" data-direction={index.direction ?? "flat"}>
            {LIGHT[index.direction ?? "flat"]}
          </span>
        </div>
        {values.length > 1 && <Sparkline series={values} label="Evolución del índice" />}
        <p className="training-card-note">
          Base 100 al empezar el periodo · media de {index.muscles}{" "}
          {index.muscles === 1 ? "grupo muscular" : "grupos musculares"}, cada uno comparando cada
          máquina consigo misma
          {stats.excluded > 0
            ? ` · ${stats.excluded} ${stats.excluded === 1 ? "día apartado" : "días apartados"} por no encajar`
            : ""}
        </p>
      </Card>
    </Section>
  );
}

function FrequencyCards({ stats }: { stats: Stats }) {
  const { frequency } = stats;
  const met = frequency.goal > 0 && frequency.done >= frequency.goal;
  const average = `media 4 sem: ${frequency.average.toFixed(1).replace(".", ",")}`;
  return (
    <Section title="Constancia">
      <div className="training-stat-pair">
        <section className="surface training-card" data-done={met || undefined}>
          <h3 className="training-card-title">Esta semana</h3>
          <p className="training-stat-figure">
            {frequency.done} <span className="training-stat-unit">de {frequency.goal}</span>
            {met && (
              <span className="training-stat-done">
                <Icon name="done" label="Objetivo cumplido" />
              </span>
            )}
          </p>
          <p className="training-card-note">{met ? `objetivo cumplido · ${average}` : average}</p>
        </section>
        <section className="surface training-card">
          <h3 className="training-card-title">Racha</h3>
          <p className="training-stat-figure">
            {frequency.streak} <span className="training-stat-unit">sem</span>
          </p>
          <p className="training-card-note">
            {frequency.streak === 0 ? "sin semanas cumplidas" : "cumpliendo objetivo"}
          </p>
        </section>
      </div>
    </Section>
  );
}

export function VolumeCard({ stats, onOpen }: { stats: Stats; onOpen: (muscle: string) => void }) {
  const most = Math.max(...stats.muscles.map((entry) => entry.sets), 20);
  return (
    <Section title="Músculos">
      <div className="surface training-card" aria-label="Músculos">
        <BodyMaps
          label="Fuerza por músculo en el periodo"
          colors={Object.fromEntries(stats.muscles.map((entry) => [entry.muscle, changeColor(entry.delta)]))}
          names={Object.fromEntries(stats.muscles.map((entry) => [entry.muscle, entry.name]))}
          onSelect={onOpen}
        />
        <p className="training-card-note">
          Verde, gana fuerza; rojo, pierde; gris, estable o sin datos. Toca un músculo para verlo.
        </p>
        <Hint>En cada músculo, la fuerza y las series por semana, con el rango de 10 a 20.</Hint>
        {REGIONS.map((region) => {
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
          <p className="training-card-note">
            Sin tu peso, dominadas y fondos no cuentan para la fuerza. Se apunta en Plan, en Ajustes.
          </p>
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
  return (
    <li>
      <button
        type="button"
        className="training-volume-row training-pressable"
        aria-label={`${entry.name}: ${
          entry.delta === null ? "sin datos de fuerza" : `fuerza ${signed(entry.delta)}`
        }, ${entry.sets.toFixed(1).replace(".", ",")} series por semana`}
        onClick={() => onOpen(entry.muscle)}
      >
        <span className="training-volume-name">{entry.name}</span>
        <span
          className="training-volume-delta"
          data-direction={entry.direction ?? undefined}
        >
          {entry.delta === null ? "—" : signed(entry.delta)}
        </span>
        <span className="training-volume-track">
          <span
            className="training-volume-fill"
            data-band={entry.band}
            style={{ "--fill-to": `${Math.min((entry.sets / most) * 100, 100)}%` } as CSSProperties}
          />
        </span>
        <span className="training-volume-value">{entry.sets.toFixed(1).replace(".", ",")}</span>
      </button>
    </li>
  );
}

function MoversCard({ stats, onOpen }: { stats: Stats; onOpen: (id: string, gym: string | null) => void }) {
  const shown = [...stats.movers.slice(0, 3), ...stats.movers.slice(-2)].filter(
    (mover, index, all) =>
      all.findIndex((other) => other.variant_id === mover.variant_id && other.gym_id === mover.gym_id) === index,
  );
  if (shown.length === 0) return null;
  return (
    <Section title="Qué sube y qué baja">
      <div className="surface training-card">
        <ul className="training-movers">
          {shown.map((mover) => (
            <li key={`${mover.variant_id}:${mover.gym_id ?? "-"}`}>
              <button type="button" className="training-mover" onClick={() => onOpen(mover.variant_id, mover.gym_id)}>
                <span className="training-mover-text">
                  <span className="training-mover-name">{exerciseLabel(mover)}</span>
                  <span className="training-card-note">
                    {mover.gym ? `${mover.gym} · ` : ""}e1RM {kg(mover.e1rm)}
                    {mover.without_pr >= 3 ? ` · sin PR en ${mover.without_pr} sesiones` : ""}
                  </span>
                </span>
                <span className="training-mover-delta" data-direction={mover.delta >= 0 ? "up" : "down"}>
                  {signed(mover.delta)}
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

function since(day: string | null): string {
  if (!day) return "nunca";
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  const days = Math.round((Date.now() - new Date(year, month - 1, date).getTime()) / 86_400_000);
  if (days <= 0) return "hoy";
  if (days === 1) return "ayer";
  if (days < 30) return `hace ${days} días`;
  return shortDay(day);
}

const MONTH = new Intl.DateTimeFormat("es-ES", { month: "short", year: "numeric" });

function month(day: string): string {
  const [year = 1970, value = 1] = day.split("-").map(Number);
  return MONTH.format(new Date(year, value - 1, 1)).replace(".", "");
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
  const load = useCallback(() => readMuscleStats(muscle, period), [muscle, period]);
  const { data: detail, failed } = useLoad<MuscleStats>(load);

  return (
    <Sheet title={detail?.name ?? "Músculo"} onClose={onClose}>
      {failed ? (
        <p className="training-field-error" role="alert">
          No se ha podido cargar este músculo.
        </p>
      ) : !detail ? (
        <Hint>
          Cargando…
        </Hint>
      ) : (
        <>
          {detail.value !== null && detail.delta !== null ? (
            <p className="training-index-value">
              {detail.value.toFixed(1).replace(".", ",")}
              <span className="training-index-delta" data-direction={detail.direction ?? "flat"}>
                {signed(detail.delta)}
              </span>
            </p>
          ) : (
            <Hint>
              Sin sesiones bastantes en este periodo para decir si su fuerza sube o baja.
            </Hint>
          )}
          {detail.trend.length > 1 && (
            <MarkedSpark
              values={detail.trend.map((point) => point.value)}
              days={detail.trend.map((point) => point.day)}
              marks={detail.changes}
              label={`Fuerza de ${detail.name.toLowerCase()}`}
            />
          )}
          <p className="training-card-note">
            Base 100 al empezar el periodo · {detail.sets.toFixed(1).replace(".", ",")} series por semana ·
            última vez {since(detail.last_day)}
            {detail.changes.length > 0 ? " · las rayas son cambios de centro o de máquina" : ""}
          </p>

          <h3 className="training-card-title">Ejercicios · todo el histórico</h3>
          {detail.exercises.length === 0 ? (
            <Hint>Ningún ejercicio lo tiene como músculo principal.</Hint>
          ) : (
            <ul className="training-movers">
              {detail.exercises.map((exercise) => (
                <li key={exercise.variant_id}>
                  <button type="button" className="training-mover" onClick={() => onOpen(exercise.variant_id)}>
                    <span className="training-mover-text">
                      <span className="training-mover-name">{exerciseLabel(exercise)}</span>
                      <span className="training-card-note">
                        {exercise.gyms.join(", ")} · {month(exercise.first_day)} – {since(exercise.last_day)} ·{" "}
                        {exercise.sessions} {exercise.sessions === 1 ? "sesión" : "sesiones"}
                        {exercise.excluded > 0 ? ` · ${exercise.excluded} apartadas` : ""}
                      </span>
                    </span>
                    {exercise.delta !== null ? (
                      <span className="training-mover-delta" data-direction={exercise.delta >= 0 ? "up" : "down"}>
                        {signed(exercise.delta)}
                      </span>
                    ) : exercise.last !== null ? (
                      <span className="training-mover-delta">{kg(exercise.last)}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button variant="secondary" block onClick={onClose}>
            Cerrar
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
      setError(reason instanceof Error ? reason.message : "No se ha podido guardar");
    }
  }

  const bodyweight = detail?.load_type !== "external";
  return (
    <Sheet title={detail ? exerciseLabel(detail) : "Variante"} onClose={onClose}>
      {failed ? (
        <p className="training-field-error" role="alert">
          No se ha podido cargar esta variante.
        </p>
      ) : !detail ? (
        <Hint>
          Cargando…
        </Hint>
      ) : !machine ? (
        <Hint>
          {bodyweight && detail.bodyweight === null
            ? "Apunta tu peso en Plan, en Ajustes, para medir este ejercicio: su carga es tu cuerpo más el lastre."
            : "Todavía no hay ninguna sesión que cuente para la fuerza con esta variante."}
        </Hint>
      ) : (
        <>
          {detail.machines.length > 1 && (
            <ChoiceChips
              label="Centro"
              value={key(machine)}
              onChange={(value) => {
                setChosen(value);
                setAll(false);
              }}
              options={detail.machines.map((candidate) => ({
                value: key(candidate),
                label: candidate.gym ?? "Sin centro",
              }))}
            />
          )}
          <Hint>
            {detail.machines.length > 1
              ? "Cada centro es otra máquina: sus kilos no se comparan entre sí."
              : machine.gym ?? "Sin centro"}
            {" · "}paso {detail.min_increment.toFixed(1).replace(".", ",")} kg
            {bodyweight ? " · la carga es tu peso más el lastre" : ""}
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
            Sesiones
            {machine.excluded > 0 ? ` · ${machine.excluded} no cuentan` : ""}
          </h3>
          <p className="training-card-note">
            Un día que se aleja más de un 30 % de las sesiones de alrededor no cuenta para la fuerza. El
            dato no se toca: tócalo para decir si era correcto, o ábrelo para corregirlo.
          </p>
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
                        {shortDay(point.day)} · {point.reps} × {kg(point.load)}
                      </span>
                      {whyNot(point) && <span className="training-card-note">{whyNot(point)}</span>}
                    </span>
                    <span className="training-point-e1rm" data-status={point.status}>
                      {kg(point.e1rm)}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
          {!all && machine.points.filter((point) => point.status === "counted").length > LIMIT && (
            <Button variant="plain" size="small" onClick={() => setAll(true)}>
              Ver todas
            </Button>
          )}

          {error && (
            <p className="training-field-error" role="alert">
              {error}
            </p>
          )}
          <Button variant="secondary" block onClick={onClose}>
            Cerrar
          </Button>
        </>
      )}
      {detail && detail.notes.length > 0 && (
        <section aria-label="Notas que lo mencionan">
          <GroupLabel count={detail.notes.length}>Notas</GroupLabel>
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
  const counted = machine.points.filter((point) => point.status === "counted");
  const first = counted[0];
  const last = counted[counted.length - 1];
  const records = recordIds(machine.points);
  const change = first && last && counted.length > 1 ? last.e1rm - first.e1rm : null;
  const said = advice(machine, increment, external);
  return (
    <>
      {machine.best && (
        <Card label="Máximo estimado">
          <HeadlineFigure
            label="Máximo estimado"
            value={formatDecimal(Math.round(machine.best.e1rm))}
            unit="kg"
            change={
              change === null
                ? undefined
                : {
                    text: `${change > 0 ? "+" : change < 0 ? "−" : "±"}${formatDecimal(Math.abs(Math.round(change * 10) / 10))} kg en ${periodLabel(period).toLowerCase()}`,
                    direction: change > 0 ? "up" : change < 0 ? "down" : "flat",
                  }
            }
          />
          {counted.length > 1 && (
            <TrendChart
              label="Máximo estimado por sesión"
              valueName="Máximo estimado"
              bandName="Tu rango normal"
              highlightName="Récord"
              flagOutside={false}
              format={(value) => `${formatDecimal(Math.round(value))} kg`}
              band={normalRange(machine.points)}
              points={counted.map((point) => ({ day: point.day, value: point.e1rm, highlight: records.has(point.id) }))}
            />
          )}
        </Card>
      )}

      {said.length > 0 && (
        <Notice title="Lo que dice">
          {said.map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
        </Notice>
      )}

      {machine.records.length > 0 && (
        <Stack>
          <GroupLabel>Récord por repeticiones</GroupLabel>
          <Card>
            <Figures
              items={machine.records.map((record) => ({
                label: `${record.range} reps`,
                value: `${formatDecimal(record.load)} kg`,
                muted: !record.reliable,
              }))}
            />
          </Card>
          {machine.records.some((record) => !record.reliable) && (
            <Hint>En gris, las estimaciones de más de diez repeticiones: poco fiables.</Hint>
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
  const changes = machine.segments.slice(1);
  const joins = machine.marks.filter((mark) => mark.kind === "join");
  if (changes.length === 0 && joins.length === 0) return null;
  return (
    <ul className="training-movers">
      {changes.map((segment) => (
        <li key={segment.since} className="training-change">
          <span className="training-mover-text">
            <span className="training-mover-name">Otra máquina desde el {longDate(segment.since)}</span>
            <span className="training-card-note">
              {segment.start === "mark"
                ? "Lo marcaste tú. Lo de antes y lo de después no se comparan."
                : `Detectado: el nivel saltó ${segment.jump === null ? "de golpe" : signed(segment.jump)} y se quedó ahí.`}
            </span>
          </span>
          {segment.start === "mark" && segment.mark_id ? (
            <Button variant="plain" size="small" onClick={() => onRemove(segment.mark_id!)}>
              Quitar
            </Button>
          ) : segment.start === "detected" ? (
            <Button variant="plain" size="small" onClick={() => onJoin(segment.since)}>
              No cambió
            </Button>
          ) : null}
        </li>
      ))}
      {joins.map((mark) => (
        <li key={mark.id} className="training-change">
          <span className="training-mover-text">
            <span className="training-mover-name">La misma máquina el {longDate(mark.day)}</span>
            <span className="training-card-note">Dijiste que no cambió, aunque el nivel saltara.</span>
          </span>
          <Button variant="plain" size="small" onClick={() => onRemove(mark.id)}>
            Deshacer
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se ha podido guardar");
      setBusy(false);
    }
  }

  const first = machine.segments.some((segment) => segment.since === point.day);
  return (
    <Sheet title={longDate(point.day)} onClose={onClose}>
      <p className="training-index-value">
        {point.reps} × {kg(point.load)}
        <span className="training-stat-unit"> · e1RM {kg(point.e1rm)}</span>
      </p>
      <Hint>
        {exerciseLabel(variant)}
        {machine.gym ? ` · ${machine.gym}` : ""}
        {variant.load_type !== "external" ? " · la carga es tu peso más el lastre" : ""}
      </Hint>
      <p className={point.status === "counted" ? "training-card-note" : "training-warning"}>
        {whyNot(point) ?? "Cuenta para la fuerza."}
      </p>

      <div className="training-sheet-actions">
        {point.verdict !== null ? (
          <Button variant="secondary" block disabled={busy} onClick={() => void act(() => clearPoint(point.id))}>
            Volver a lo automático
          </Button>
        ) : point.status === "counted" ? (
          <Button variant="secondary" block disabled={busy} onClick={() => void act(() => judgePoint(point.id, "excluded"))}>
            Apartar este día
          </Button>
        ) : (
          <Button variant="secondary" block disabled={busy} onClick={() => void act(() => judgePoint(point.id, "counted"))}>
            Es correcto: que cuente
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
            La máquina cambió desde este día
          </Button>
        )}
        {onOpenSession && (
          <Button variant="plain" block disabled={busy} onClick={() => onOpenSession(point.session_id)}>
            Abrir la sesión para corregirla
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
