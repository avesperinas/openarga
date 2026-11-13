"use client";

import * as React from "react";

import { Button, Stepper } from "./controls";
import { Card, Hint } from "./screen";
import { TrendChart } from "./trend";
import { locale, timeZone } from "./regional";

export interface BodyWeightDay {
  day: string;
  kg: number;
}

export interface BodyWeightHistory {
  days: BodyWeightDay[];
  latest: BodyWeightDay | null;
  pending?: boolean;
}

export interface BodyWeightCardProps {
  history: BodyWeightHistory | null;
  onLog: (kg: number) => Promise<unknown> | void;
  today?: string;
  note?: string;
  window?: number;
}

const DAY_MS = 86_400_000;
const stamp = (day: string): number => Date.parse(`${day}T00:00:00Z`);

const kilos = (value: number): string =>
  value.toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function weighedOn(day: string, today: string): string {
  const ago = Math.round((stamp(today) - stamp(day)) / DAY_MS);
  if (ago === 0) return "hoy";
  if (ago === 1) return "ayer";
  return new Date(stamp(day)).toLocaleDateString(locale(), {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    ...(ago > 300 ? { year: "numeric" } : {}),
  });
}

export function weightChange(days: BodyWeightDay[], back = 30): number | null {
  const last = days[days.length - 1];
  if (!last) return null;
  const target = stamp(last.day) - back * DAY_MS;
  const before = days.filter((one) => stamp(one.day) <= target);
  const reference = before[before.length - 1];
  if (!reference || target - stamp(reference.day) > back * DAY_MS) return null;
  return Math.round((last.kg - reference.kg) * 10) / 10;
}

export function BodyWeightCard({ history, onLog, today, note, window: span = 180 }: BodyWeightCardProps) {
  const now = today ?? new Date().toLocaleDateString("sv-SE", { timeZone: timeZone() });
  const latest = history?.latest ?? null;
  const [draft, setDraft] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const value = draft ?? latest?.kg ?? null;

  const from = stamp(now) - span * DAY_MS;
  const shown = (history?.days ?? []).filter((one) => stamp(one.day) >= from);
  const change = weightChange(history?.days ?? []);

  const log = () => {
    if (value == null || busy) return;
    setBusy(true);
    Promise.resolve(onLog(value))
      .then(() => setDraft(null))
      .catch(() => undefined)
      .finally(() => setBusy(false));
  };

  return (
    <Card title="Peso">
      <div className="body-weight">
        {latest ? (
          <p className="body-weight-figure">
            <span className="body-weight-value">{kilos(latest.kg)}</span>
            <span className="body-weight-unit">kg</span>
            <span className="body-weight-when">
              {weighedOn(latest.day, now)}
              {change != null && change !== 0 && ` · ${change > 0 ? "+" : "−"}${kilos(Math.abs(change))} kg en 30 días`}
            </span>
          </p>
        ) : (
          <Hint>{history ? "Aún no hay ningún peso apuntado." : "Cargando…"}</Hint>
        )}
        {shown.length > 1 && (
          <TrendChart
            label="Peso"
            valueName="Peso"
            points={shown.map((one) => ({ day: one.day, value: one.kg }))}
            format={(kg) => `${kilos(kg)} kg`}
          />
        )}
        <div className="body-weight-log">
          <Stepper label="Peso de hoy" value={value} step={0.1} min={20} max={400} unit="kg" inputMode="decimal" onChange={setDraft} />
          <Button variant="tinted" onClick={log} disabled={value == null || busy || !history}>
            {busy ? "Apuntando…" : "Apuntar"}
          </Button>
        </div>
        <Hint>
          {history?.pending
            ? "Apuntado aquí. Llegará a Salud en cuanto conteste."
            : (note ?? "El mismo peso en Salud, Macros y Training.")}
        </Hint>
      </div>
    </Card>
  );
}
