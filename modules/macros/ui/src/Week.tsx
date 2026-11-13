import {
  Card,
  Columns,
  CoverageList,
  EmptyState,
  ErrorState,
  Figures,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Notice,
  OfflineNotice,
  Screen,
  SegmentedControl,
  Sheet,
  Skeleton,
  Switch,
  TrendChart,
  type Translate,
  useT,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import {
  type Contributors,
  type Suggestions,
  type Trend,
  type Week,
  Unauthorised,
  readDay,
  readSuggestions,
  readTrend,
  readWeek,
  readWeekContributors,
  signIn,
} from "./api";
import { coverageNote, figure } from "./DayDetail";
import { coverageGroups, daysNear, energyLine, kcalTrend, windowLine } from "./eating";
import { ExpenditureCard } from "./Expenditure";
import { ScreenHeader } from "./Header";
import { amount, shiftDay, todayIso } from "./words";

const wide = () => typeof window !== "undefined" && window.matchMedia("(min-width: 1100px)").matches;

export function WeekScreen({ onAdd }: { onAdd?: () => void }) {
  const t = useT();
  const [found, setFound] = useState<Week | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [tips, setTips] = useState<Suggestions | null>(null);
  const [all, setAll] = useState(false);
  const [span, setSpan] = useState<"4" | "8">(wide() ? "8" : "4");
  const [asking, setAsking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const today = todayIso();
    readDay(today)
      .then((day) => (day.complete ? today : shiftDay(today, -1)))
      .catch(() => shiftDay(today, -1))
      .then((last) => {
        readTrend(last, 8).then(setTrend).catch(() => setTrend(null));
        readSuggestions(last).then(setTips).catch(() => setTips(null));
        return readWeek(last, all);
      })
      .then((next) => {
        setFound(next);
        setError(null);
      })
      .catch((reason: unknown) => {
        if (reason instanceof Unauthorised) return signIn();
        setError(reason instanceof Error ? reason.message : t("week.load_failed"));
      });
  }, [all, t]);

  useEffect(load, [load]);

  const kcalGoal = (found?.goals ?? []).find((goal) => goal.nutrient === "kcal");
  const low = kcalGoal?.min ?? null;
  const high = kcalGoal?.max ?? null;
  const aim = low !== null && high !== null ? (low + high) / 2 : (high ?? low);
  const average = found?.averages.kcal ?? null;
  const near = found ? daysNear(found, aim) : null;
  const groups = found ? coverageGroups(found, trend, t, setAsking) : [];
  const points = trend ? kcalTrend(trend, Number(span)) : [];

  return (
    <Screen wide>
      <ScreenHeader eyebrow={found ? windowLine(found, t) : undefined} title={t("week.title")} />
      <OfflineNotice />
      {!found && error ? (
        <ErrorState title={t("common.not_answering")} detail={error} onRetry={load} />
      ) : !found ? (
        <Skeleton rows={6} />
      ) : found.days_logged === 0 ? (
        <EmptyState
          icon="chart"
          hue={4}
          title={t("week.empty")}
          action={onAdd ? { label: t("common.log"), icon: "plus", onClick: onAdd } : undefined}
        >
          <p>{t("week.empty_detail")}</p>
        </EmptyState>
      ) : (
        <>
          {found.counted && !found.counted.complete && (
            <Notice tone="info">
              {t("week.few_complete", { days: found.counted.days })}
            </Notice>
          )}
          <Card>
            <GroupLabel>{t("nutrient.kcal")}</GroupLabel>
            <Figures
              label={t("week.energy")}
              items={[
                { label: t("week.kcal_mean"), value: average === null ? "—" : amount(average, 0) },
                { label: t("week.goal"), value: aim ? amount(aim, 0) : "—" },
                ...(near && aim ? [{ label: t("week.days_near"), value: t("common.n_of", { n: near.near, of: near.of }) }] : []),
              ]}
            />
            <SegmentedControl
              label={t("week.span")}
              options={[
                { value: "4", label: t("week.weeks", { count: 4 }) },
                { value: "8", label: t("week.weeks", { count: 8 }) },
              ]}
              value={span}
              onChange={setSpan}
            />
            {points.length > 1 ? (
              <TrendChart
                label={t("week.trend")}
                points={points}
                band={aim ? { low: aim * 0.9, high: aim * 1.1 } : null}
                bandName={t("week.near_goal")}
                valueName={t("week.complete_day")}
                averageName={t("week.mean_7")}
                format={(value) => `${amount(value, 0)} kcal`}
              />
            ) : (
              <Hint>{t("week.trend_soon")}</Hint>
            )}
            <Hint>{energyLine(average, low, high, found, t)}</Hint>
          </Card>

          <Columns count={2} stack>
            <Card>
              <GroupLabel>{t("week.title")}</GroupLabel>
              {!found.profile.from_health && <Hint>{t("week.no_profile")}</Hint>}
              {groups.map((group) => (
                <div key={group.key} className="macros-coverage-group">
                  <GroupLabel count={group.items.length} tone={group.key === "caution" ? "warning" : undefined}>
                    {group.title}
                  </GroupLabel>
                  <CoverageList label={group.title} items={group.items} />
                </div>
              ))}
              <div className="macros-switch">
                <span>{t("week.all_micros")}</span>
                <Switch label={t("week.all_micros")} checked={all} onChange={setAll} />
              </div>
            </Card>
            <Improve tips={tips} onAdd={onAdd} />
          </Columns>

          {found.expenditure && <ExpenditureCard found={found.expenditure} kcalGoal={high} onChanged={load} />}
        </>
      )}
      {asking && found && <WeekContributors last={found.last} nutrient={asking} onClose={() => setAsking(null)} />}
    </Screen>
  );
}

function Improve({ tips, onAdd }: { tips: Suggestions | null; onAdd?: () => void }) {
  const t = useT();
  if (!tips) return null;
  return (
    <Card>
      <GroupLabel>{t("improve.title")}</GroupLabel>
      {tips.nutrients.length === 0 ? (
        <EmptyState icon="done" hue={2} title={t("improve.all")}>
          <p>{t("improve.good")}</p>
        </EmptyState>
      ) : (
        tips.nutrients.map((nutrient) => (
          <div key={nutrient.key} className="macros-coverage-group">
            <GroupLabel>
              {t("improve.nutrient", {
                name: nutrient.name,
                value: amount(nutrient.average, nutrient.average >= 10 ? 0 : 1),
                reference: amount(nutrient.reference, nutrient.reference >= 10 ? 0 : 1),
                unit: nutrient.unit,
              })}
            </GroupLabel>
            {nutrient.foods.length === 0 ? (
              <Hint>{t("improve.nothing", { name: nutrient.name.toLowerCase() })}</Hint>
            ) : (
              <List>
                {nutrient.foods.map((food) => (
                  <ListRow
                    key={food.food_id ?? food.recipe_id ?? food.name}
                    title={food.name}
                    subtitle={`${food.portion} · ${sinceLabel(food.last_eaten, t)}`}
                    value={`+${amount(food.amount, food.amount >= 10 ? 0 : 1)} ${nutrient.unit}`}
                    onClick={onAdd}
                  />
                ))}
              </List>
            )}
          </div>
        ))
      )}
      <Hint>{t("improve.source")}</Hint>
    </Card>
  );
}

export function sinceLabel(day: string, t: Translate, now: Date = new Date()): string {
  const days = Math.round((now.getTime() - new Date(`${day}T12:00:00`).getTime()) / 86_400_000);
  if (days <= 0) return t("since.today");
  if (days === 1) return t("since.yesterday");
  return t("since.days", { count: days });
}

function WeekContributors({ last, nutrient, onClose }: { last: string; nutrient: string; onClose: () => void }) {
  const t = useT();
  const [found, setFound] = useState<Contributors | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    readWeekContributors(last, nutrient)
      .then(setFound)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : t("common.load_failed")));
  }, [last, nutrient, t]);
  return (
    <Sheet title={found?.name ?? t("contributors.title")} onClose={onClose}>
      {error && <Notice tone="warning">{error}</Notice>}
      {!found && !error && <Skeleton rows={3} />}
      {found && (
        <>
          <Hint>
            {found.total === null
              ? t("contributors.none")
              : t("contributors.week_total", { value: figure(found.total, found.unit) })}
            {coverageNote(found.coverage, t) ? ` ${coverageNote(found.coverage, t)}.` : ""}
          </Hint>
          <List>
            {found.items.map((one) => (
              <ListRow
                key={one.name}
                title={one.name}
                subtitle={one.times > 1 ? t("contributors.times", { count: one.times }) : undefined}
                value={`${figure(one.value, found.unit)} · ${amount(one.share, 0)} %`}
              />
            ))}
          </List>
        </>
      )}
    </Sheet>
  );
}
