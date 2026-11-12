"use client";

import * as React from "react";

export type CareerHue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export function monthRange(from: string, to: string): string[] {
  const out: string[] = [];
  let [year = 0, month = 1] = from.split("-").map(Number);
  const end = to.slice(0, 7);
  for (let guard = 0; guard < 1200; guard++) {
    const key = `${year}-${String(month).padStart(2, "0")}`;
    if (key > end) break;
    out.push(key);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

export interface PeriodSpan {
  key: string;
  name: string;
  hue: CareerHue;
  from: string;
  to: string | null;
  muted?: boolean;
}

export function spanPlaces(spans: PeriodSpan[], months: string[]): { span: PeriodSpan; left: number; width: number }[] {
  const count = months.length;
  if (count === 0) return [];
  const first = months[0]!;
  const last = months[count - 1]!;
  return spans.flatMap((span) => {
    const to = span.to ?? last;
    if (to < first || span.from > last) return [];
    const start = Math.max(0, months.indexOf(span.from < first ? first : span.from));
    const endKey = to > last ? last : to;
    const end = months.indexOf(endKey);
    if (end < start) return [];
    return [{ span, left: start / count, width: (end - start + 1) / count }];
  });
}

export function SpanRibbon({
  spans,
  months,
  label,
  onSelect,
  align,
}: {
  spans: PeriodSpan[];
  months: string[];
  label: string;
  onSelect?: (key: string) => void;
  align?: "series-chart";
}) {
  const places = spanPlaces(spans, months);
  return (
    <ul className="span-ribbon" aria-label={label} data-align={align}>
      {places.map(({ span, left, width }) => {
        const body = (
          <span className="span-ribbon-name" data-hidden={width < 0.12 || undefined}>
            {span.name}
          </span>
        );
        const description = `${span.name}, de ${span.from} a ${span.to ?? "hoy"}`;
        return (
          <li
            key={span.key}
            className="span-ribbon-span"
            data-hue={span.hue}
            data-muted={span.muted || undefined}
            style={{ left: `${left * 100}%`, width: `${width * 100}%` }}
          >
            {onSelect ? (
              <button type="button" aria-label={description} onClick={() => onSelect(span.key)}>
                {body}
              </button>
            ) : (
              <span aria-label={description}>{body}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export interface PeriodGroup {
  key: string;
  name: string;
  hue: CareerHue;
}

export interface PeriodPart {
  group: string;
  value: number;
  estimated?: boolean;
}

export interface Period {
  key: string;
  label: string;
  parts: PeriodPart[];
  projected?: boolean;
}

const BW = 100;
const BH = 50;

export function PeriodBars({
  periods,
  groups,
  label,
  format = (value) => value.toLocaleString("es-ES"),
  axisFormat,
  spans,
  onSpan,
  selected,
  onSelect,
}: {
  periods: Period[];
  groups: PeriodGroup[];
  label: string;
  format?: (value: number) => string;
  axisFormat?: (value: number) => string;
  spans?: PeriodSpan[];
  onSpan?: (key: string) => void;
  selected?: string | null;
  onSelect?: (key: string) => void;
}) {
  const [hover, setHover] = React.useState<number | null>(null);
  const pattern = React.useId().replace(/:/g, "");
  const count = periods.length;
  const totals = periods.map((one) => one.parts.reduce((sum, part) => sum + Math.max(0, part.value), 0));
  const top = niceTop(Math.max(0, ...totals));
  const y = (value: number) => BH - (value / top) * BH;
  const step = BW / Math.max(1, count);
  const width = Math.max(step * 0.7, Math.min(step, 0.35));
  const hueOf = new Map(groups.map((group) => [group.key, group.hue]));
  const nameOf = new Map(groups.map((group) => [group.key, group.name]));
  const today = periods.findIndex((one) => one.projected);
  const months = periods.map((one) => one.key);
  const shown = hover ?? (selected ? months.indexOf(selected) : -1);
  const firstJanuary = periods.findIndex((one) => one.key.endsWith("-01"));
  const showFirst = firstJanuary === -1 || firstJanuary > count * 0.1;
  const used = groups.filter((group) => periods.some((one) => one.parts.some((part) => part.group === group.key && part.value)));

  if (count === 0) return <p className="widget-note">Sin datos todavía</p>;

  return (
    <figure className="period-bars" aria-label={label}>
      <div className="period-bars-plot">
        <ul className="period-bars-ticks" aria-hidden="true">
          {[top, top / 2].map((value) => (
            <li key={value} style={{ top: `${(y(value) / BH) * 100}%` }}>
              {(axisFormat ?? format)(value)}
            </li>
          ))}
        </ul>
        <svg viewBox={`0 0 ${BW} ${BH}`} preserveAspectRatio="none" role="img" aria-label={label}>
          <defs>
            <pattern id={pattern} width="1.2" height="1.2" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line className="period-bars-hatch" x1="0" y1="0" x2="0" y2="1.2" />
            </pattern>
          </defs>
          {[top, top / 2].map((value) => (
            <line key={value} className="period-bars-grid" x1="0" x2={BW} y1={y(value)} y2={y(value)} />
          ))}
          {periods.map((one, index) => {
            let level = 0;
            const x = index * step + (step - width) / 2;
            return (
              <g key={one.key} data-projected={one.projected || undefined} data-selected={index === shown || undefined}>
                {one.parts.map((part, at) => {
                  if (!(part.value > 0)) return null;
                  const from = level;
                  level += part.value;
                  const box = { x, width, y: y(level), height: Math.max(0.2, y(from) - y(level)) };
                  return (
                    <React.Fragment key={`${part.group}-${at}`}>
                      <rect className="period-bars-bar" data-hue={hueOf.get(part.group) ?? 8} {...box} />
                      {part.estimated && <rect className="period-bars-estimated" fill={`url(#${pattern})`} {...box} />}
                    </React.Fragment>
                  );
                })}
              </g>
            );
          })}
          {today > 0 && <line className="period-bars-today" x1={today * step} x2={today * step} y1="0" y2={BH} />}
        </svg>
        {today > 0 && (
          <span className="period-bars-today-label" style={{ left: `${(today / count) * 100}%` }} aria-hidden="true">
            hoy
          </span>
        )}
        <div className="period-bars-hits" style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}>
          {periods.map((one, index) => (
            <button
              key={one.key}
              type="button"
              aria-label={`${one.label}${one.projected ? ", previsto" : ""}: ${format(totals[index] ?? 0)}`}
              aria-pressed={onSelect ? one.key === selected : undefined}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(index)}
              onBlur={() => setHover(null)}
              onClick={() => onSelect?.(one.key)}
            />
          ))}
        </div>
        {shown >= 0 && periods[shown] && (
          <div
            className="series-chart-tip"
            role="status"
            style={{ left: `${((shown + 0.5) / count) * 100}%` }}
            data-side={shown > count / 2 ? "left" : "right"}
          >
            <p className="series-chart-tip-title">
              {periods[shown]!.label}
              {periods[shown]!.projected ? " · previsto" : ""}
            </p>
            {periods[shown]!.parts.map((part, at) => (
              <p key={`${part.group}-${at}`} className="series-chart-tip-row">
                <span className="period-bars-swatch" data-hue={hueOf.get(part.group) ?? 8} aria-hidden="true" />
                <span>
                  {nameOf.get(part.group) ?? part.group}
                  {part.estimated ? " ≈" : ""}
                </span>
                <span className="series-chart-tip-value">{format(part.value)}</span>
              </p>
            ))}
          </div>
        )}
      </div>
      <ul className="period-bars-years" aria-hidden="true">
        {periods.map((one, index) =>
          one.key.endsWith("-01") || (index === 0 && showFirst) ? (
            <li key={one.key} style={{ left: `${(index / count) * 100}%` }}>
              {one.key.slice(0, 4)}
            </li>
          ) : null,
        )}
      </ul>
      {spans && spans.length > 0 && <SpanRibbon spans={spans} months={months} label="Contratos" onSelect={onSpan} />}
      {used.length > 0 && (
        <ul className="period-bars-legend">
          {used.map((group) => (
            <li key={group.key}>
              <span className="period-bars-swatch" data-hue={group.hue} aria-hidden="true" />
              {group.name}
            </li>
          ))}
          {periods.some((one) => one.parts.some((part) => part.estimated)) && (
            <li>
              <span className="period-bars-swatch" data-estimated="" aria-hidden="true" />
              Reconstruido
            </li>
          )}
          {today > 0 && (
            <li>
              <span className="period-bars-swatch" data-projected="" aria-hidden="true" />
              Previsto
            </li>
          )}
        </ul>
      )}
    </figure>
  );
}

function niceTop(value: number): number {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const found = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((one) => one * power >= value) ?? 10;
  return found * power;
}

export type DotState = "matched" | "differs" | "missing" | "estimated" | "projected" | "empty";

export interface MonthDot {
  key: string;
  label: string;
  state: DotState;
  description: string;
}

export function MonthDots({
  items,
  label,
  onSelect,
}: {
  items: MonthDot[];
  label: string;
  onSelect?: (key: string) => void;
}) {
  return (
    <ol className="month-dots" aria-label={label} style={{ gridTemplateColumns: `repeat(${Math.max(1, items.length)}, minmax(0, 1fr))` }}>
      {items.map((item) => {
        const body = (
          <>
            <span className="month-dots-dot" data-state={item.state} aria-hidden="true" />
            <span className="month-dots-label" aria-hidden="true">
              {item.label}
            </span>
          </>
        );
        return (
          <li key={item.key} className="month-dots-item" title={item.description}>
            {onSelect && item.state !== "empty" && item.state !== "projected" ? (
              <button type="button" aria-label={item.description} onClick={() => onSelect(item.key)}>
                {body}
              </button>
            ) : (
              <span role="img" aria-label={item.description}>
                {body}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export interface WaterfallStep {
  key: string;
  label: string;
  value: number;
  kind: "total" | "change" | "result";
  tone?: "positive" | "negative" | "warning" | "neutral";
}

export function waterfallBars(steps: WaterfallStep[]): { step: WaterfallStep; from: number; to: number }[] {
  let level = 0;
  return steps.map((step) => {
    if (step.kind === "change") {
      const from = level;
      level += step.value;
      return { step, from, to: level };
    }
    if (step.kind === "total") level = step.value;
    return { step, from: 0, to: step.value };
  });
}

export function Waterfall({
  steps,
  label,
  format = (value) => value.toLocaleString("es-ES"),
}: {
  steps: WaterfallStep[];
  label: string;
  format?: (value: number) => string;
}) {
  const bars = waterfallBars(steps);
  const values = bars.flatMap((bar) => [bar.from, bar.to]);
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  const span = max - min || 1;
  const at = (value: number) => ((max - value) / span) * 100;
  return (
    <figure className="waterfall" aria-label={label}>
      <ol className="waterfall-bars" style={{ gridTemplateColumns: `repeat(${Math.max(1, bars.length)}, minmax(0, 1fr))` }}>
        {bars.map(({ step, from, to }) => {
          const high = Math.max(from, to);
          const low = Math.min(from, to);
          const shown = step.kind === "change" ? (step.value < 0 ? "−" : "+") + format(Math.abs(step.value)) : format(step.value);
          return (
            <li key={step.key} className="waterfall-step" aria-label={`${step.label}: ${shown}`}>
              <span className="waterfall-track" aria-hidden="true">
                <span
                  className="waterfall-bar"
                  data-kind={step.kind}
                  data-tone={step.tone ?? "neutral"}
                  style={{ top: `${at(high)}%`, height: `${Math.max(0.8, at(low) - at(high))}%` }}
                >
                  <span className="waterfall-value">{shown}</span>
                </span>
                {min < 0 && <span className="waterfall-zero" style={{ top: `${at(0)}%` }} />}
              </span>
              <span className="waterfall-label" aria-hidden="true">
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
    </figure>
  );
}
