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
    .toLocaleLowerCase("es-ES");

const asText = (value: number | null | undefined) =>
  value === null || value === undefined ? "" : String(value).replace(".", ",");

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

  const unit = source === "metric" ? unitWord(metric?.unit) : "";
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
    }, "No se ha podido guardar");

  if (deleting && goal) {
    return (
      <ConfirmDelete
        title="¿Borrar esta meta?"
        subject={goal.title}
        consequence="Se borra con todo lo apuntado. Si solo la dejas, mejor abandónala: se queda en el histórico."
        action="Borrar meta"
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
      title={goal ? "Meta" : "Nueva meta"}
      onClose={onClose}
      action={{ label: busy ? "Guardando…" : goal ? "Guardar" : "Añadir", onClick: save, disabled: busy || !ready }}
    >
      <div className="goals-form">
        <TextField
          label="Qué te propones"
          value={title}
          placeholder={kind === "periodic" ? "Leer 20 minutos" : "Bajar a 80 kg"}
          autoFocus={!goal}
          onChange={setTitle}
        />
        <ChoiceChips
          label="Categoría"
          options={[
            ...categories.map((one) => ({ value: one.id, label: one.name })),
            { value: NONE, label: "Sin categoría" },
          ]}
          value={categoryId}
          onChange={setCategoryId}
        />
        {!goal && (
          <SegmentedControl<GoalKind>
            label="Clase"
            options={[
              { value: "periodic", label: "Cada día o semana" },
              { value: "dated", label: "Con fecha" },
            ]}
            value={kind}
            onChange={setKind}
          />
        )}

        <SegmentedControl<Source>
          label="Cómo se sabe"
          options={[
            { value: "manual", label: "A mano" },
            { value: "metric", label: "Una cifra de arga" },
          ]}
          value={source}
          onChange={setSource}
        />
        {source === "metric" &&
          (metric ? (
            <List>
              <ListRow
                title={metric.label}
                subtitle={`Último: ${figure(metric.last_value, metric.unit)} · ${shortDate(metric.last_day, today)}`}
                action={{ icon: "close", label: "Cambiar de cifra", onClick: () => setMetric(null) }}
              />
            </List>
          ) : metrics === null ? (
            <Hint>Buscando las cifras que llegan…</Hint>
          ) : metrics.length === 0 ? (
            <Hint>
              Todavía no llega ninguna cifra de otras apps. Cuando Vitals, Money o las demás las publiquen,
              saldrán aquí. Mientras, apúntala a mano.
            </Hint>
          ) : (
            <>
              <SearchField label="Buscar una cifra" value={search} onChange={setSearch} placeholder="Pasos, peso, patrimonio…" />
              <List>
                {found.slice(0, 30).map((one) => (
                  <ListRow
                    key={one.key}
                    title={one.label}
                    value={figure(one.last_value, one.unit)}
                    subtitle={`${one.kind === "amount" ? "Se suma" : "Vale lo último"} · ${shortDate(one.last_day, today)}`}
                    onClick={() => pick(one)}
                  />
                ))}
              </List>
            </>
          ))}

        {kind === "periodic" ? (
          <>
            <SegmentedControl<Period>
              label="Cómo se cuenta"
              options={[
                { value: "day", label: "Días por semana" },
                { value: "week", label: "Total de la semana" },
              ]}
              value={period}
              onChange={setPeriod}
            />
            {period === "day" && (
              <Stepper
                label="Días por semana"
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
                label="Qué es"
                options={[
                  { value: "figure", label: "Llegar a una cifra" },
                  { value: "milestone", label: "Un hito" },
                ]}
                value={shape}
                onChange={setShape}
              />
            )}
            <DateField
              label="Para cuándo"
              value={due}
              onChange={(value) => value && setDue(value)}
              invalid={!goal && due <= today}
              hint={!goal && due <= today ? "Tiene que ser más adelante que hoy." : undefined}
            />
          </>
        )}

        {!milestone && (kind === "dated" || needsTarget || source === "manual") && (
          <>
            <ChoiceChips<Direction>
              label="Sentido"
              options={[
                { value: "at_least", label: "Al menos" },
                { value: "at_most", label: "Como mucho" },
              ]}
              value={direction}
              onChange={setDirection}
            />
            <TextField
              label={
                kind === "dated"
                  ? `Objetivo${unit ? ` (${unit})` : ""}`
                  : period === "week"
                    ? `Total de la semana${unit ? ` (${unit})` : ""}`
                    : `Condición de cada día${unit ? ` (${unit})` : ""}`
              }
              value={target}
              inputMode="decimal"
              placeholder={kind === "periodic" && period === "day" && source === "manual" ? "Opcional" : ""}
              hint={
                kind === "periodic" && period === "day" && source === "manual"
                  ? "Sin condición, cada día se marca hecho o no."
                  : undefined
              }
              onChange={setTarget}
            />
          </>
        )}

        {kind === "dated" && !milestone && (
          <TextField
            label={`Punto de partida${unit ? ` (${unit})` : ""}`}
            value={start}
            inputMode="decimal"
            placeholder={
              metric?.kind === "amount" ? "0" : goal && source === "metric" ? "Lo que valía al empezar" : "El valor de hoy"
            }
            hint={
              metric?.kind === "amount"
                ? "Cuenta lo sumado desde hoy: los libros terminados, los pasos."
                : source === "manual"
                  ? "Después apuntas dónde vas cuando quieras."
                  : undefined
            }
            onChange={setStart}
          />
        )}

        <TextField label="Nota" value={note} placeholder="Opcional" onChange={setNote} />
        <Switch label="Destacada en el escritorio" checked={featured} onChange={setFeatured} />
        {goal && (
          <Button variant="destructive" icon="trash" block onClick={() => setDeleting(true)}>
            Borrar meta
          </Button>
        )}
        <Problem error={error} />
      </div>
    </Sheet>
  );
}
