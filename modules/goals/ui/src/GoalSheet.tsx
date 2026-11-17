import {
  Button,
  ChoiceChips,
  ConfirmDelete,
  DateField,
  Hint,
  List,
  ListRow,
  parseDecimal,
  SearchField,
  SegmentedControl,
  Sheet,
  Stepper,
  Switch,
  TextField,
  numbers,
  regional,
  useT,
} from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import {
  type Direction,
  type Goal,
  type GoalIn,
  type GoalKind,
  type Metric,
  type Period,
  createGoal,
  readMetrics,
  removeGoal,
  updateGoal,
} from "./api";
import { figure, shortDate, unitWord } from "./goalWords";
import { Problem, useBusy, useCategories } from "./Parts";
import { addDays } from "./words";

const NONE = "none";
type Source = "manual" | "metric";
type DatedShape = "figure" | "milestone";

const fold = (text: string) =>
  text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLocaleLowerCase(regional().locale);

const asText = (value: number | null | undefined) =>
  value === null || value === undefined ? "" : numbers({ useGrouping: false, maximumFractionDigits: 6 }).format(value);

export function GoalSheet({
  goal,
  today,
  onClose,
  onSaved,
}: {
  goal?: Goal;
  today: string;
  onClose: () => void;
  onSaved: (goal: Goal | null) => void;
}) {
  const t = useT();
  const { list: categories } = useCategories();
  const [title, setTitle] = useState(goal?.title ?? "");
  const [categoryId, setCategoryId] = useState<string>(goal?.category_id ?? NONE);
  const [kind, setKind] = useState<GoalKind>(goal?.kind ?? "periodic");
  const [source, setSource] = useState<Source>(goal?.metric ? "metric" : "manual");
  const [metric, setMetric] = useState<Metric | null>(
    goal?.metric ? { ...goal.metric, last_day: goal.last_day ?? today, last_value: goal.current ?? 0 } : null,
  );
  const [metrics, setMetrics] = useState<Metric[] | null>(null);
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState<Direction>(goal?.direction ?? "at_least");
  const [target, setTarget] = useState(asText(goal?.target));
  const [period, setPeriod] = useState<Period>(goal?.period ?? "day");
  const [daysPerWeek, setDaysPerWeek] = useState<number>(goal?.days_per_week ?? 7);
  const [shape, setShape] = useState<DatedShape>(goal && goal.kind === "dated" && goal.target === null ? "milestone" : "figure");
  const [start, setStart] = useState(asText(goal?.start_value));
  const [due, setDue] = useState(goal?.due_on ?? addDays(today, 90));
  const [note, setNote] = useState(goal?.note ?? "");
  const [featured, setFeatured] = useState(goal?.featured ?? false);
  const [deleting, setDeleting] = useState(false);
  const { busy, error, run } = useBusy();

  useEffect(() => {
    if (source !== "metric" || metrics) return;
    readMetrics()
      .then(setMetrics)
      .catch(() => setMetrics([]));
  }, [source, metrics]);

  const found = useMemo(() => {
    const wanted = fold(search.trim());
    return (metrics ?? []).filter((one) => !wanted || fold(`${one.label} ${one.key}`).includes(wanted));
  }, [metrics, search]);

  const unit = source === "metric" ? unitWord(t, metric?.unit) : "";
  const withUnit = (label: string) => (unit ? `${label} (${unit})` : label);
  const milestone = kind === "dated" && shape === "milestone" && source === "manual";
  const needsTarget =
    (kind === "periodic" && (period === "week" || source === "metric")) || (kind === "dated" && !milestone);
  const targetValue = parseDecimal(target);
  const ready =
    title.trim() !== "" &&
    (!needsTarget || targetValue !== null) &&
    (source === "manual" || metric !== null) &&
    (kind === "periodic" || due > today || Boolean(goal));

  const pick = (chosen: Metric) => {
    setMetric(chosen);
    if (!title.trim()) setTitle(chosen.label);
    if (goal) {
      if (chosen.key !== goal.metric?.key) setStart("");
    } else if (chosen.kind === "level" && !start) setStart(asText(chosen.last_value));
  };

  const save = () =>
    void run(async () => {
      const body: GoalIn = {
        title: title.trim(),
        category_id: categoryId === NONE ? null : categoryId,
        kind,
        metric_key: source === "metric" ? (metric?.key ?? null) : null,
        direction,
        target: milestone || (!needsTarget && target.trim() === "") ? null : targetValue,
        period: kind === "periodic" ? period : null,
        days_per_week: kind === "periodic" && period === "day" ? daysPerWeek : null,
        start_value: kind === "dated" && !milestone && start.trim() !== "" ? parseDecimal(start) : null,
        start_on: goal ? goal.start_on : null,
        due_on: kind === "dated" ? due : null,
        note: note.trim() || null,
        featured,
      };
      onSaved(goal ? await updateGoal(goal.id, body) : await createGoal(body));
    }, t("sheet.save_failed"));

  if (deleting && goal) {
    return (
      <ConfirmDelete
        title={t("goal_sheet.delete_question")}
        subject={goal.title}
        consequence={t("goal_sheet.delete_consequence")}
        action={t("goal_sheet.delete")}
        onCancel={() => setDeleting(false)}
        onConfirm={async () => {
          await removeGoal(goal.id);
          onSaved(null);
        }}
      />
    );
  }

  return (
    <Sheet
      title={goal ? t("goals.goal") : t("goal_sheet.new")}
      onClose={onClose}
      action={{ label: busy ? t("sheet.saving") : goal ? t("sheet.save") : t("sheet.add"), onClick: save, disabled: busy || !ready }}
    >
      <div className="goals-form">
        <TextField
          label={t("goal_sheet.what")}
          value={title}
          placeholder={kind === "periodic" ? t("goal_sheet.what_periodic") : t("goal_sheet.what_dated")}
          autoFocus={!goal}
          onChange={setTitle}
        />
        <ChoiceChips
          label={t("home.category")}
          options={[
            ...categories.map((one) => ({ value: one.id, label: one.name })),
            { value: NONE, label: t("group.no_category") },
          ]}
          value={categoryId}
          onChange={setCategoryId}
        />
        {!goal && (
          <SegmentedControl<GoalKind>
            label={t("goal_sheet.kind")}
            options={[
              { value: "periodic", label: t("goal_sheet.periodic") },
              { value: "dated", label: t("group.dated") },
            ]}
            value={kind}
            onChange={setKind}
          />
        )}

        <SegmentedControl<Source>
          label={t("goal_sheet.source")}
          options={[
            { value: "manual", label: t("goal_sheet.manual") },
            { value: "metric", label: t("goal_sheet.metric") },
          ]}
          value={source}
          onChange={setSource}
        />
        {source === "metric" &&
          (metric ? (
            <List>
              <ListRow
                title={metric.label}
                subtitle={t("goal_sheet.last", { value: figure(t, metric.last_value, metric.unit), day: shortDate(metric.last_day, today) })}
                action={{ icon: "close", label: t("goal_sheet.change_metric"), onClick: () => setMetric(null) }}
              />
            </List>
          ) : metrics === null ? (
            <Hint>{t("goal_sheet.searching")}</Hint>
          ) : metrics.length === 0 ? (
            <Hint>{t("goal_sheet.no_metrics")}</Hint>
          ) : (
            <>
              <SearchField label={t("goal_sheet.search")} value={search} onChange={setSearch} placeholder={t("goal_sheet.search_placeholder")} />
              <List>
                {found.slice(0, 30).map((one) => (
                  <ListRow
                    key={one.key}
                    title={one.label}
                    value={figure(t, one.last_value, one.unit)}
                    subtitle={`${one.kind === "amount" ? t("goal_sheet.amount") : t("goal_sheet.level")} · ${shortDate(one.last_day, today)}`}
                    onClick={() => pick(one)}
                  />
                ))}
              </List>
            </>
          ))}

        {kind === "periodic" ? (
          <>
            <SegmentedControl<Period>
              label={t("goal_sheet.counted")}
              options={[
                { value: "day", label: t("goal_sheet.days_per_week") },
                { value: "week", label: t("goal_sheet.week_total") },
              ]}
              value={period}
              onChange={setPeriod}
            />
            {period === "day" && (
              <Stepper
                label={t("goal_sheet.days_per_week")}
                value={daysPerWeek}
                step={1}
                min={1}
                max={7}
                inputMode="numeric"
                onChange={(value) => setDaysPerWeek(value ?? 7)}
              />
            )}
          </>
        ) : (
          <>
            {source === "manual" && (
              <SegmentedControl<DatedShape>
                label={t("goal_sheet.what_is")}
                options={[
                  { value: "figure", label: t("goal_sheet.reach_figure") },
                  { value: "milestone", label: t("goal_sheet.a_milestone") },
                ]}
                value={shape}
                onChange={setShape}
              />
            )}
            <DateField
              label={t("task.when")}
              value={due}
              onChange={(value) => value && setDue(value)}
              invalid={!goal && due <= today}
              hint={!goal && due <= today ? t("goal_sheet.later_than_today") : undefined}
            />
          </>
        )}

        {!milestone && (kind === "dated" || needsTarget || source === "manual") && (
          <>
            <ChoiceChips<Direction>
              label={t("goal_sheet.direction")}
              options={[
                { value: "at_least", label: t("goal_sheet.at_least") },
                { value: "at_most", label: t("goal_sheet.at_most") },
              ]}
              value={direction}
              onChange={setDirection}
            />
            <TextField
              label={
                kind === "dated"
                  ? withUnit(t("goal.target"))
                  : period === "week"
                    ? withUnit(t("goal_sheet.week_total"))
                    : withUnit(t("goal_sheet.daily_condition"))
              }
              value={target}
              inputMode="decimal"
              placeholder={kind === "periodic" && period === "day" && source === "manual" ? t("sheet.optional") : ""}
              hint={
                kind === "periodic" && period === "day" && source === "manual"
                  ? t("goal_sheet.no_condition")
                  : undefined
              }
              onChange={setTarget}
            />
          </>
        )}

        {kind === "dated" && !milestone && (
          <TextField
            label={withUnit(t("goal_sheet.start"))}
            value={start}
            inputMode="decimal"
            placeholder={
              metric?.kind === "amount" ? "0" : goal && source === "metric" ? t("goal_sheet.start_was") : t("goal_sheet.start_today")
            }
            hint={
              metric?.kind === "amount"
                ? t("goal_sheet.amount_hint")
                : source === "manual"
                  ? t("goal_sheet.manual_hint")
                  : undefined
            }
            onChange={setStart}
          />
        )}

        <TextField label={t("goal.note")} value={note} placeholder={t("sheet.optional")} onChange={setNote} />
        <Switch label={t("goal_sheet.featured")} checked={featured} onChange={setFeatured} />
        {goal && (
          <Button variant="destructive" icon="trash" block onClick={() => setDeleting(true)}>
            {t("goal_sheet.delete")}
          </Button>
        )}
        <Problem error={error} />
      </div>
    </Sheet>
  );
}
