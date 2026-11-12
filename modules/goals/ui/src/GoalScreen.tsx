import { useResource } from "@openarga/app";
import {
  Button,
  DateField,
  EmptyState,
  ErrorState,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  parseDecimal,
  Screen,
  Section,
  Skeleton,
  StatRow,
  StatTile,
  TextField,
  TrendChart,
  type TrendPoint,
  useToast,
  YearCalendar,
} from "@openarga/ui";
import { useState } from "react";

import {
  type Goal,
  type GoalDetail,
  changed,
  checkGoal,
  closeGoal,
  readGoal,
  reopenGoal,
  uncheckGoal,
} from "./api";
import { GoalSheet } from "./GoalSheet";
import { figure, frequency, shortDate, standing, subtitle, unitWord, weekLabel } from "./goalWords";
import { ScreenHeader } from "./Header";
import { Problem, useBusy } from "./Parts";
import { capital, longDate, todayIso } from "./words";

export function chartPoints(detail: GoalDetail): TrendPoint[] {
  const { goal, history } = detail;
  const withValue = history.filter((point) => point.value !== null && point.day >= goal.start_on);
  if (goal.metric?.kind !== "amount") {
    return history.filter((point) => point.value !== null).map((point) => ({ day: point.day, value: point.value! }));
  }
  let total = goal.start ?? 0;
  return withValue.map((point) => {
    total += point.value!;
    return { day: point.day, value: total };
  });
}

const asksValueOf = (goal: Goal) => (goal.kind === "dated" ? goal.target !== null : goal.period === "week");

export function GoalScreen({ id, onBack }: { id: string; onBack: () => void }) {
  const found = useResource(`goal:${id}`, () => readGoal(id), { persist: true });
  const detail = found.data ?? null;
  const missing = Boolean(found.error?.message.startsWith("no existe"));
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [day, setDay] = useState(todayIso());
  const { busy, error: failed, run } = useBusy();
  const toast = useToast();
  const today = todayIso();

  const load = changed;

  const back = { label: "KPIs", onClick: onBack };
  if (missing) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <EmptyState icon="alert" title="No se encuentra esta meta" action={{ label: "Volver", onClick: onBack }}>
          <p>{found.error?.message}</p>
        </EmptyState>
      </Screen>
    );
  }
  if (!detail) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <OfflineNotice />
        {found.error ? (
          <ErrorState detail={found.error.message} onRetry={found.refresh} />
        ) : (
          <Skeleton rows={5} />
        )}
      </Screen>
    );
  }

  const { goal, history } = detail;
  const unit = goal.metric?.unit ?? null;
  const said = standing(goal);
  const active = goal.status === "active";
  const manual = history
    .filter((point) => point.manual)
    .reverse()
    .slice(0, goal.kind === "periodic" && !asksValueOf(goal) ? 10 : 60);
  const asksValue = asksValueOf(goal);

  const act = (action: () => Promise<Goal>, message: string) =>
    void run(async () => {
      await action();
      toast({ message });
      load();
    }, "No se ha podido");

  const log = () =>
    void run(async () => {
      const amount = parseDecimal(value);
      if (amount === null) throw new Error("Escribe una cifra");
      await checkGoal(goal.id, { day, value: amount });
      setValue("");
      load();
    }, "No se ha podido apuntar");

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={subtitle(goal, today)} title={goal.title} />
      <OfflineNotice />

      {goal.kind === "periodic" ? (
        <StatRow label="Cómo vas">
          <StatTile
            label="Racha"
            value={`${goal.streak ?? 0} ${goal.streak_unit === "weeks" ? "sem." : "días"}`}
            foot={goal.streak_unit === "weeks" ? "semanas seguidas cumplidas" : "días seguidos"}
            tone={goal.streak ? "positive" : "neutral"}
          />
          <StatTile
            label="Esta semana"
            value={weekLabel(goal).replace(" esta semana", "")}
            foot={goal.week_met ? "Cumplida" : frequency(goal)}
            tone={goal.week_met ? "positive" : "neutral"}
            progress={goal.week_target ? (goal.week_count ?? 0) / goal.week_target : null}
          />
          <StatTile
            label="Constancia"
            value={goal.constancy === null ? "—" : `${Math.round(goal.constancy * 100)} %`}
            foot="en las últimas 4 semanas"
          />
        </StatRow>
      ) : goal.target !== null ? (
        <StatRow label="Cómo vas">
          <StatTile
            label={active ? "Ahora" : "Al cerrar"}
            value={figure(active ? goal.current : goal.closed_value, unit)}
            foot={said.text}
            tone={said.tone}
            progress={goal.progress}
          />
          <StatTile
            label="Objetivo"
            value={figure(goal.target, unit)}
            foot={goal.due_on ? `${shortDate(goal.due_on, today)}${active && goal.days_left !== null ? ` · faltan ${goal.days_left} días` : ""}` : undefined}
          />
          {active && (
            <StatTile
              label="Si sigues así"
              value={goal.projection === null ? "—" : figure(goal.projection, unit)}
              foot={
                goal.projection === null
                  ? "Hacen falta dos datos en 4 semanas"
                  : goal.projection_reached
                    ? "Llegas"
                    : "No llegas"
              }
              tone={goal.projection === null ? "neutral" : goal.projection_reached ? "positive" : "negative"}
            />
          )}
        </StatRow>
      ) : (
        <StatRow label="Cómo vas">
          <StatTile label="Hito" value={said.text} tone={said.tone} foot={goal.due_on ? shortDate(goal.due_on, today) : undefined} />
        </StatRow>
      )}

      {goal.kind === "periodic" ? (
        <Section title="Cada día">
          <YearCalendar
            label={`Días cumplidos de ${goal.title}`}
            days={history.map((point) => ({ day: point.day, value: point.met ? 1 : 0 }))}
            end={today}
            goal={1}
            format={(one) => (one >= 1 ? "cumplido" : "no")}
          />
        </Section>
      ) : goal.target !== null && chartPoints(detail).length > 0 ? (
        <Section title={goal.metric ? goal.metric.label : "Lo apuntado"}>
          <TrendChart
            label={goal.title}
            points={chartPoints(detail)}
            band={goal.direction === "at_least" ? { low: goal.target } : { high: goal.target }}
            valueName={goal.metric?.kind === "amount" ? "Sumado" : "Valor"}
            format={(one) => figure(one, unit)}
          />
        </Section>
      ) : null}

      {active && goal.kind === "periodic" && goal.period === "day" && (
        <Section title="Hoy">
          <div className="goals-row-actions">
            <Button
              icon="done"
              variant={goal.today_met ? "secondary" : "primary"}
              onClick={() =>
                act(() => checkGoal(goal.id, { done: !goal.today_met }), goal.today_met ? "Hoy, no" : "Hecho hoy")
              }
            >
              {goal.today_met ? "Hoy no" : "Hecho hoy"}
            </Button>
          </div>
        </Section>
      )}

      {active && asksValue && (
        <Section title={goal.metric ? "Apuntar a mano un día" : "Apuntar dónde vas"}>
          <div className="goals-form">
            <TextField
              label={`Cifra${unitWord(unit) ? ` (${unitWord(unit)})` : ""}`}
              value={value}
              inputMode="decimal"
              onChange={setValue}
              onSubmit={log}
            />
            <DateField label="Día" value={day} max={today} onChange={(one) => one && setDay(one)} />
            <Button icon="plus" disabled={busy || !value.trim()} onClick={log}>
              Apuntar
            </Button>
          </div>
        </Section>
      )}

      {active && goal.kind === "dated" && goal.target === null && (
        <Button icon="done" block onClick={() => act(() => checkGoal(goal.id, { done: true }), "Hito cumplido")}>
          Ya está hecho
        </Button>
      )}

      {manual.length > 0 && (
        <Section title="Apuntado a mano">
          <List>
            {manual.map((point) => (
              <ListRow
                key={point.day}
                title={capital(longDate(point.day))}
                value={point.value !== null ? figure(point.value, unit) : point.done ? "Hecho" : "No"}
                subtitle={point.note ?? undefined}
                action={
                  active
                    ? {
                        icon: "undo",
                        label: `Quitar lo apuntado el ${point.day}`,
                        onClick: () => act(() => uncheckGoal(goal.id, point.day), "Quitado"),
                      }
                    : undefined
                }
              />
            ))}
          </List>
        </Section>
      )}

      {goal.note && (
        <Section title="Nota">
          <Hint>{goal.note}</Hint>
        </Section>
      )}

      <div className="goals-row-actions">
        <Button icon="edit" variant="secondary" onClick={() => setEditing(true)}>
          Editar
        </Button>
        {active ? (
          <>
            {goal.kind === "dated" && (
              <Button variant="secondary" icon="done" onClick={() => act(() => closeGoal(goal.id, "achieved"), "Cumplida")}>
                Dar por cumplida
              </Button>
            )}
            <Button variant="secondary" icon="close" onClick={() => act(() => closeGoal(goal.id, "abandoned"), "Abandonada")}>
              Abandonar
            </Button>
          </>
        ) : (
          <Button variant="secondary" icon="undo" onClick={() => act(() => reopenGoal(goal.id), "Reabierta")}>
            Reabrir
          </Button>
        )}
      </div>
      <Problem error={failed} />

      {editing && (
        <GoalSheet
          goal={goal}
          today={today}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            if (saved) load();
            else {
              changed();
              onBack();
            }
          }}
        />
      )}
    </Screen>
  );
}
