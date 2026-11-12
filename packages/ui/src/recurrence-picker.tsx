import * as React from "react";
import {
  CheckChips,
  ChoiceChips,
  SegmentedControl,
  Stepper,
} from "./controls";
import { DateField } from "./date-field";
import {
  DAY_NAMES,
  MONTH_NAMES,
  ORDINALS,
  WEEKDAYS,
  describe,
  positionOf,
  quickRules,
  rule,
  toRRule,
  weekdayOf,
  type Freq,
  type RecurrenceRule,
  type Weekday,
} from "./recurrence";

export interface RecurrencePickerProps {
  date: string;
  value: RecurrenceRule | null;
  onChange: (value: RecurrenceRule | null) => void;
  label?: string;
}

const NEVER = "never";
const CUSTOM = "custom";

const FREQS: { value: Freq; label: string }[] = [
  { value: "daily", label: "Días" },
  { value: "weekly", label: "Semanas" },
  { value: "monthly", label: "Meses" },
  { value: "yearly", label: "Años" },
];

type Ends = "never" | "until" | "count";
type Anchor = "day" | "position" | "last";

const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

function ends(value: RecurrenceRule): Pick<RecurrenceRule, "count" | "until"> {
  return value.count !== undefined
    ? { count: value.count }
    : value.until
      ? { until: value.until }
      : {};
}

function anchorOf(value: RecurrenceRule): Anchor {
  if (value.byDay.some((d) => d.pos !== undefined)) return "position";
  if (value.byMonthDay.includes(-1)) return "last";
  return "day";
}

export function RecurrencePicker({
  date,
  value,
  onChange,
  label = "Repetir",
}: RecurrencePickerProps) {
  const quick = React.useMemo(() => quickRules(date), [date]);
  const current = value ? toRRule(value) : NEVER;
  const matchesQuick = value === null || quick.some((q) => q.key === current);
  const [customising, setCustomising] = React.useState(!matchesQuick);
  const custom = customising || !matchesQuick;

  const weekday = weekdayOf(date);
  const [, month, day] = date.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  const pos = positionOf(date);

  const choose = (key: string) => {
    if (key === CUSTOM) {
      setCustomising(true);
      if (value === null) onChange(rule("weekly", { byDay: [{ weekday }] }));
      return;
    }
    setCustomising(false);
    onChange(
      key === NEVER ? null : (quick.find((q) => q.key === key)?.rule ?? null),
    );
  };

  const shaped = (
    freq: Freq,
    anchor: Anchor,
    keep: RecurrenceRule,
  ): RecurrenceRule => {
    const base = { interval: keep.interval, ...ends(keep) };
    if (freq === "daily") return rule("daily", base);
    if (freq === "weekly") {
      const days =
        keep.freq === "weekly" && keep.byDay.length
          ? keep.byDay
          : [{ weekday }];
      return rule("weekly", { ...base, byDay: days });
    }
    const byMonth = freq === "yearly" ? [month] : [];
    if (anchor === "position")
      return rule(freq, { ...base, byMonth, byDay: [{ weekday, pos }] });
    if (anchor === "last")
      return rule(freq, { ...base, byMonth, byMonthDay: [-1] });
    return rule(freq, { ...base, byMonth, byMonthDay: [day] });
  };

  const chips = [
    { value: NEVER, label: "No se repite" },
    ...quick.map((q) => ({ value: q.key, label: q.label })),
    { value: CUSTOM, label: "Personalizar…" },
  ];

  const ending: Ends =
    value?.count !== undefined ? "count" : value?.until ? "until" : "never";
  const setEnding = (next: Ends) => {
    if (!value) return;
    const rest = { ...value };
    delete rest.count;
    delete rest.until;
    if (next === "never") onChange(rest);
    if (next === "count") onChange({ ...rest, count: 10 });
    if (next === "until") onChange({ ...rest, until: defaultUntil(date) });
  };

  const whereLabel =
    value?.freq === "yearly" ? ` de ${MONTH_NAMES[month - 1]}` : "";
  const anchors: { value: Anchor; label: string }[] = [
    { value: "day", label: `El ${day}${whereLabel}` },
    {
      value: "position",
      label: capital(`${ORDINALS[pos]} ${DAY_NAMES[weekday].one}${whereLabel}`),
    },
    { value: "last", label: `Último día${whereLabel}` },
  ];

  return (
    <fieldset className="recurrence">
      <legend className="recurrence-legend">{label}</legend>
      <ChoiceChips
        label={label}
        options={chips}
        value={custom ? CUSTOM : current}
        onChange={choose}
      />

      {custom && value && (
        <div className="recurrence-detail">
          <div className="recurrence-every">
            <span className="recurrence-caption">Cada</span>
            <Stepper
              label="Intervalo"
              value={value.interval}
              step={1}
              min={1}
              max={99}
              inputMode="numeric"
              onChange={(next) => onChange({ ...value, interval: next ?? 1 })}
            />
          </div>
          <ChoiceChips<Freq>
            label="Frecuencia"
            options={FREQS}
            value={value.freq}
            onChange={(freq) => onChange(shaped(freq, anchorOf(value), value))}
          />

          {value.freq === "weekly" && (
            <div className="recurrence-weekdays">
              <CheckChips<Weekday>
                label="Días de la semana"
                options={WEEKDAYS.map((w) => ({
                  value: w,
                  label: DAY_NAMES[w].one.slice(0, 3),
                }))}
                values={value.byDay.map((d) => d.weekday)}
                onChange={(days) => {
                  if (days.length === 0) return;
                  onChange({
                    ...value,
                    byDay: days.map((w) => ({ weekday: w })),
                  });
                }}
              />
            </div>
          )}

          {(value.freq === "monthly" || value.freq === "yearly") && (
            <ChoiceChips<Anchor>
              label="Qué día"
              options={anchors}
              value={anchorOf(value)}
              onChange={(anchor) => onChange(shaped(value.freq, anchor, value))}
            />
          )}

          <div className="recurrence-ends">
            <span className="recurrence-caption">Termina</span>
            <SegmentedControl<Ends>
              label="Termina"
              options={[
                { value: "never", label: "Nunca" },
                { value: "until", label: "Un día" },
                { value: "count", label: "Veces" },
              ]}
              value={ending}
              onChange={setEnding}
            />
            {ending === "until" && (
              <DateField
                label="Hasta el día"
                value={value.until?.slice(0, 10) ?? ""}
                onChange={(until) => until && onChange({ ...value, until })}
              />
            )}
            {ending === "count" && (
              <Stepper
                label="Veces"
                value={value.count ?? 10}
                step={1}
                min={1}
                max={999}
                unit="veces"
                inputMode="numeric"
                onChange={(count) => onChange({ ...value, count: count ?? 1 })}
              />
            )}
          </div>
        </div>
      )}

      <p className="recurrence-phrase" aria-live="polite">
        {value ? capital(describe(value)) : "Solo una vez"}
      </p>
    </fieldset>
  );
}

function defaultUntil(date: string): string {
  const [y, m, d] = date.split("-").map(Number) as [number, number, number];
  const end = new Date(Date.UTC(y, m - 1 + 3, d));
  return end.toISOString().slice(0, 10);
}
