import { useResource } from "@openarga/app";
import {
  Button,
  GroupLabel,
  Inline,
  Panes,
  Collapsible,
  CreateButton,
  ErrorState,
  Hint,
  IconButton,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  Section,
  Skeleton,
  SwipeArea,
  useToast,
} from "@openarga/ui";
import { useState } from "react";

import { AddSheet } from "./AddSheet";
import { DayDetail, DaySummary } from "./DayDetail";
import { MealSheet, type MealStep } from "./MealSheet";
import { OutdatedNotice } from "./Planning";
import {
  type Day,
  type Entry,
  type Item,
  type Meal,
  confirmEntry,
  unconfirmEntry,
  readDay,
  readUsualOf,
  readWeek,
  removeEntry,
  repeatItems,
  repeatMeal,
  setDayComplete,
} from "./api";
import { ExpenditureCard } from "./Expenditure";
import { ScreenHeader } from "./Header";
import { DishSheet } from "./DishSheet";
import { ItemSheet } from "./ItemSheet";
import {
  amount,
  dayTitle,
  doubtLine,
  itemTag,
  longDate,
  quantityLabel,
  rows,
  shiftDay,
  timeOf,
  todayIso,
} from "./words";

export function mealNow(day: Day | undefined): Meal | undefined {
  return day?.meals.find((one) => one.current);
}

export function TodayScreen({
  day,
  add = false,
  onDay,
  onAddDone,
  onWeek,
}: {
  onWeek?: () => void;
  day?: string;
  add?: boolean;
  onDay: (day: string) => void;
  onAddDone?: () => void;
}) {
  const today = todayIso();
  const shown = day ?? today;
  const found = useResource(`day:${shown}`, () => readDay(shown), {
    persist: true,
  });
  const [adding, setAddingState] = useState<Meal["meal"] | true | null>(
    add ? true : null,
  );
  const setAdding = (next: Meal["meal"] | true | null) => {
    setAddingState(next);
    if (next === null && add) onAddDone?.();
  };
  const [open, setOpen] = useState<{ entry: Entry; item: Item } | null>(null);
  const [dish, setDish] = useState<{ entry: Entry; dish: string } | null>(null);
  const [openMeal, setOpenMeal] = useState<{
    meal: Meal;
    step: MealStep;
  } | null>(null);
  const toast = useToast();
  const reload = () => void found.refresh();
  const data = found.data;
  const now = mealNow(data);

  const confirm = (entry: Entry) =>
    void confirmEntry(entry.id)
      .then(() => {
        toast({
          message: `Apuntado · ${entry.said ?? entry.items.map((one) => one.name).join(", ")}`,
          action: {
            label: "Deshacer",
            run: () => void unconfirmEntry(entry.id).then(reload),
          },
        });
        reload();
      })
      .catch((reason: unknown) =>
        toast({
          message:
            reason instanceof Error
              ? reason.message
              : "No se ha podido confirmar",
          tone: "error",
        }),
      );

  const complete = (done: boolean) =>
    void setDayComplete(shown, done)
      .then(() => {
        reload();
        if (done)
          toast({
            message: "Día completo",
            action: { label: "Deshacer", run: () => complete(false) },
          });
      })
      .catch((reason: unknown) =>
        toast({
          message:
            reason instanceof Error
              ? reason.message
              : "No se ha podido guardar",
          tone: "error",
        }),
      );

  return (
    <Screen wide>
      <SwipeArea
        onNext={() => {
          const next = shiftDay(shown, 1);
          if (next <= today) onDay(next);
        }}
        onPrevious={() => onDay(shiftDay(shown, -1))}
      >
        <ScreenHeader
          eyebrow={shown === today ? longDate(today) : undefined}
          title={dayTitle(shown, today)}
        />
        <div className="macros-daynav">
          <IconButton
            icon="chevron-left"
            label="Día anterior"
            onClick={() => onDay(shiftDay(shown, -1))}
          />
          {shown !== today && (
            <Button onClick={() => onDay(today)}>Volver a hoy</Button>
          )}
          <IconButton
            icon="chevron-right"
            label="Día siguiente"
            disabled={shown >= today}
            onClick={() => onDay(shiftDay(shown, 1))}
          />
        </div>
        <OfflineNotice />

        {!data ? (
          found.error ? (
            <ErrorState
              title="Macros no contesta"
              detail={found.error.message}
              onRetry={found.refresh}
            />
          ) : (
            <Skeleton rows={6} />
          )
        ) : (
          <Panes
            asideLabel="Lo del día"
            main={
              <>
                {data.entries.length > 0 && <DaySummary day={data} />}
                {data.entries.length === 0 && (
                  <Hint>
                    Lo normal es contárselo a Claude: «un café con leche y una
                    tostada».
                  </Hint>
                )}
                {shown === today && <OutdatedNotice onChanged={reload} />}

                {data.meals.map((meal) => (
                  <MealBlock
                    key={meal.meal}
                    meal={meal}
                    today={shown === today}
                    day={shown}
                    onLogged={reload}
                    entries={data.entries.filter(
                      (entry) => entry.meal === meal.meal,
                    )}
                    planned={(data.planned ?? []).filter(
                      (entry) => entry.meal === meal.meal,
                    )}
                    onAdd={() => setAdding(meal.meal)}
                    onItem={(entry, item) => setOpen({ entry, item })}
                    onAct={(step) => setOpenMeal({ meal, step })}
                    onConfirm={confirm}
                onDish={(entry, dish) => setDish({ entry, dish })}
                  />
                ))}

                {data.entries.some((entry) =>
                  entry.items.some((item) => item.kind === "quick"),
                ) && (
                  <Hint>
                    Lo apuntado a ojo solo dice sus kcal: los micros de ese día
                    salen a medias.
                  </Hint>
                )}

                {data.entries.length > 0 && (
                  <List>
                    <ListRow
                      title={
                        data.complete ? "Día completo" : "¿Está todo apuntado?"
                      }
                      subtitle={
                        data.complete
                          ? "Cuenta para el gasto estimado"
                          : "Márcalo al acabar el día: solo los completos cuentan para el gasto estimado"
                      }
                      action={
                        data.complete
                          ? {
                              icon: "undo",
                              label: "Ya no está completo",
                              onClick: () => complete(false),
                            }
                          : {
                              icon: "done",
                              kind: "check",
                              label: "Día completo",
                              onClick: () => complete(true),
                            }
                      }
                    />
                  </List>
                )}
              </>
            }
            aside={
              <>
                {shown === today && isMonday(today) && (
                  <MondayProposal
                    kcalGoal={data.target?.kcal ?? null}
                    onChanged={reload}
                  />
                )}

                {data.entries.length > 0 && (
                  <>
                    <Collapsible
                      title="Objetivos y micronutrientes"
                      subtitle={goalsLine(data.goals ?? [])}
                    >
                      <DayDetail day={data} only="goals" />
                      <DayDetail day={data} only="groups" />
                    </Collapsible>
                    <Collapsible
                      title="El día por horas"
                      subtitle="Las kcal de cada hora y la cafeína"
                    >
                      <DayDetail day={data} only="hours" />
                    </Collapsible>
                  </>
                )}
                {onWeek && (
                  <Button variant="plain" icon="chart" onClick={onWeek}>
                    Ver cómo comes esta semana
                  </Button>
                )}
              </>
            }
          />
        )}
      </SwipeArea>

      <CreateButton
        label={now?.label ?? "Añadir"}
        onClick={() => setAdding(now?.meal ?? true)}
      />

      {adding !== null && (
        <AddSheet
          day={shown}
          meal={adding === true ? undefined : adding}
          today={data}
          onClose={() => setAdding(null)}
          onSaved={(entry, what) => {
            setAdding(null);
            reload();
            toast({
              message: `Apuntado · ${what}`,
              action: {
                label: "Deshacer",
                run: () => void removeEntry(entry.id).then(reload),
              },
            });
          }}
        />
      )}
      {open && (
        <ItemSheet
          entry={open.entry}
          item={open.item}
          meals={data?.meals ?? []}
          onClose={() => setOpen(null)}
          onChanged={() => {
            setOpen(null);
            reload();
          }}
        />
      )}
      {dish && (
        <DishSheet
          entry={dish.entry}
          dish={dish.dish}
          onItem={(item) => {
            setDish(null);
            setOpen({ entry: dish.entry, item });
          }}
          onClose={() => setDish(null)}
          onChanged={(message) => {
            setDish(null);
            reload();
            if (message) toast(message);
          }}
        />
      )}
      {openMeal && data && (
        <MealSheet
          day={shown}
          meal={openMeal.meal}
          step={openMeal.step}
          entries={data.entries.filter(
            (entry) => entry.meal === openMeal.meal.meal,
          )}
          onClose={() => setOpenMeal(null)}
          onChanged={(message) => {
            setOpenMeal(null);
            reload();
            if (message) toast({ message });
          }}
        />
      )}
    </Screen>
  );
}

export function tookLabel(entry: Pick<Entry, "items">): string {
  const taken = entry.items.every(
    (item) =>
      item.unit === "unit" || item.unit === "ml" || item.kind === "water",
  );
  return taken ? "Me lo he tomado" : "Me lo he comido";
}

export function plannedLabel(entry: Pick<Entry, "eaten_at" | "said">): string {
  return ["Planificado", timeOf(entry.eaten_at), entry.said]
    .filter(Boolean)
    .join(" · ");
}

export function goalsLine(goals: { status: string }[]): string {
  const counted = goals.filter((goal) => goal.status !== "none");
  if (counted.length === 0) return "Sin objetivos con dato todavía";
  const ok = counted.filter((goal) => goal.status === "ok").length;
  return `${ok} de ${counted.length} en zona`;
}

export function mealTitle(
  meal: Pick<Meal, "label" | "kcal">,
  empty: boolean,
): string {
  return empty ? meal.label : `${meal.label} · ${amount(meal.kcal, 0)} kcal`;
}

function MealBlock({
  meal,
  today,
  day,
  onLogged,
  entries,
  planned,
  onAdd,
  onItem,
  onAct,
  onConfirm,
  onDish,
}: {
  meal: Meal;
  today: boolean;
  day: string;
  onLogged: () => void;
  entries: Entry[];
  planned: Entry[];
  onAdd: () => void;
  onItem: (entry: Entry, item: Item) => void;
  onAct: (step: MealStep) => void;
  onConfirm: (entry: Entry) => void;
  onDish: (entry: Entry, dish: string) => void;
}) {
  const said = entries
    .map((entry) => entry.said)
    .filter((one): one is string => Boolean(one));
  const empty = entries.length === 0 && planned.length === 0;
  const name = meal.label.toLowerCase();
  return (
    <Section
      title={mealTitle(meal, entries.length === 0)}
      action={{ label: "Añadir", icon: "plus", onClick: onAdd }}
      menu={
        entries.length === 0
          ? undefined
          : {
              label: `Acciones de ${name}`,
              items: [
                ...(today
                  ? []
                  : [
                      {
                        label: "Repetir hoy",
                        icon: "repeat" as const,
                        onSelect: () => onAct("repeat"),
                      },
                    ]),
                {
                  label: "Cambiar la hora",
                  icon: "clock",
                  onSelect: () => onAct("time"),
                },
                {
                  label: "Guardar como menú",
                  icon: "bookmark",
                  onSelect: () => onAct("menu"),
                },
                {
                  label: "Borrar",
                  icon: "trash",
                  tone: "danger",
                  onSelect: () => onAct("delete"),
                },
              ],
            }
      }
    >
      {said.map((one) => (
        <Hint key={one}>
          «{one}»
        </Hint>
      ))}
      {empty && meal.started && (
        <UsualRows meal={meal} day={day} onLogged={onLogged} />
      )}
      {entries.length > 0 && (
        <List>
          {entries.flatMap((entry) =>
            rows(entry.items).map((row) => {
              if (row.kind === "dish") {
                const doubt = row.items.find((one) => one.doubt);
                return (
                  <ListRow
                    key={`${entry.id}:${row.name}`}
                    title={row.name}
                    subtitle={doubt ? `${doubtLine(doubt.doubt)} · ${doubt.name}` : row.items.map((one) => one.name).join(", ")}
                    tone={doubt ? "warning" : undefined}
                    value={`${amount(row.items.reduce((sum, one) => sum + (one.nutrients.kcal ?? 0), 0), 0)} kcal`}
                    accessory="chevron-right"
                    onClick={() => onDish(entry, row.name)}
                  />
                );
              }
              const item = row.item;
              return (
                <ListRow
                  key={item.id}
                  title={item.name}
                  subtitle={
                    item.doubt
                      ? `${doubtLine(item.doubt)} · tócalo para confirmar`
                      : [quantityLabel(item), itemTag(item)]
                          .filter(Boolean)
                          .join(" · ")
                  }
                  tone={item.doubt ? "warning" : undefined}
                  value={
                    item.kind === "water"
                      ? ""
                      : `${amount(item.nutrients.kcal ?? 0, 0)} kcal`
                  }
                  onClick={() => onItem(entry, item)}
                />
              );
            }),
          )}
        </List>
      )}
      {planned.map((entry) => (
        <div key={entry.id} className="macros-planned">
          {planned.length > 1 && <GroupLabel>{plannedLabel(entry)}</GroupLabel>}
          <List>
            {entry.items.map((item) => (
              <ListRow
                key={item.id}
                title={item.name}
                subtitle={`Planificado · ${quantityLabel(item)}`}
                value={
                  item.kind === "water"
                    ? ""
                    : `${amount(item.nutrients.kcal ?? 0, 0)} kcal`
                }
                muted
                onClick={() => onItem(entry, item)}
              />
            ))}
          </List>
          <Inline
            label={`Lo planificado: ${entry.items.map((one) => one.name).join(", ")}`}
          >
            <Button
              size="small"
              variant="tinted"
              icon="done"
              onClick={() => onConfirm(entry)}
            >
              {tookLabel(entry)}
            </Button>
            <Button
              size="small"
              variant="plain"
              onClick={() => entry.items[0] && onItem(entry, entry.items[0])}
            >
              Cambiar
            </Button>
          </Inline>
        </div>
      ))}
    </Section>
  );
}

function UsualRows({
  meal,
  day,
  onLogged,
}: {
  meal: Meal;
  day: string;
  onLogged: () => void;
}) {
  const found = useResource(`usual:${day}:${meal.meal}`, () =>
    readUsualOf(meal.meal, day),
  );
  const toast = useToast();
  const usual = found.data;
  if (!usual || (usual.yesterday.length === 0 && !usual.usual)) return null;

  const logged = (request: Promise<Entry>, what: string) =>
    void request
      .then((entry) => {
        onLogged();
        toast({
          message: `Apuntado · ${what}`,
          action: {
            label: "Deshacer",
            run: () => void removeEntry(entry.id).then(onLogged),
          },
        });
      })
      .catch((reason: unknown) =>
        toast({
          message:
            reason instanceof Error
              ? reason.message
              : "No se ha podido apuntar",
          tone: "error",
        }),
      );

  const kcal = usual.yesterday.reduce(
    (total, one) => total + (one.kcal ?? 0),
    0,
  );
  return (
    <List>
      {usual.yesterday.length > 0 && (
        <ListRow
          title="Como ayer"
          subtitle={`${usual.yesterday.map((one) => one.name).join(" + ")} · ${amount(kcal, 0)} kcal`}
          action={{
            icon: "plus",
            label: `Apuntar como ayer en ${meal.label.toLowerCase()}`,
            onClick: () =>
              logged(
                repeatMeal(shiftDay(day, -1), meal.meal, day),
                `${meal.label} como ayer`,
              ),
          }}
        />
      )}
      {usual.usual && (
        <ListRow
          title="Lo de siempre"
          subtitle={`${usual.usual.label} · ${amount(usual.usual.kcal, 0)} kcal`}
          action={{
            icon: "plus",
            label: `Apuntar lo de siempre en ${meal.label.toLowerCase()}`,
            onClick: () =>
              logged(
                repeatItems(usual.usual!.item_ids, meal.meal, day),
                usual.usual!.label,
              ),
          }}
        />
      )}
    </List>
  );
}

export function isMonday(day: string): boolean {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay() === 1;
}

export function worthProposing(
  kcal: number | null | undefined,
  goal: number | null,
): boolean {
  if (!kcal) return false;
  return goal === null || Math.abs(kcal - goal) / goal > 0.05;
}

function MondayProposal({
  kcalGoal,
  onChanged,
}: {
  kcalGoal: number | null;
  onChanged: () => void;
}) {
  const today = todayIso();
  const week = useResource(`week:${today}`, () => readWeek(today));
  const found = week.data?.expenditure;
  const lose = found?.proposals.find((one) => one.rate_kg_week < 0);
  if (!found || !lose || !worthProposing(lose.kcal, kcalGoal)) return null;
  return (
    <ExpenditureCard
      found={found}
      kcalGoal={kcalGoal}
      onChanged={onChanged}
      only={lose.rate_kg_week}
    />
  );
}
