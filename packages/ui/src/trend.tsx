"use client";

import * as React from "react";

export interface TrendPoint {
  day: string;
  value: number;
  average?: number | null;
  highlight?: boolean;
}

export interface TrendBand {
  low?: number | null;
  high?: number | null;
}

export interface TrendChartProps {
  points: TrendPoint[];
  label: string;
  band?: TrendBand | null;
  bandName?: string;
  valueName?: string;
  averageName?: string;
  format?: (value: number) => string;
  formatDay?: (day: string) => string;
  marker?: TrendMarker | null;
  highlightName?: string;
  flagOutside?: boolean;
}

export interface TrendMarker {
  day: string;
  label: string;
}

const W = 100;
const H = 60;
const MAX_DOTS = 60;

const DAY_MS = 86_400_000;

function dayNumber(day: string): number {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  return Date.UTC(year, month - 1, date) / DAY_MS;
}

export function trendDomain(points: TrendPoint[], band?: TrendBand | null): { min: number; max: number } {
  const values = points.flatMap((one) => [one.value, ...(one.average == null ? [] : [one.average])]);
  if (band?.low != null) values.push(band.low);
  if (band?.high != null) values.push(band.high);
  if (values.length === 0) return { min: 0, max: 1 };
  const low = Math.min(...values);
  const high = Math.max(...values);
  const pad = high === low ? 1 : (high - low) * 0.12;
  return { min: low - pad, max: high + pad };
}

export function trendX(points: TrendPoint[]): number[] {
  const head = points[0];
  const tail = points[points.length - 1];
  if (!head || !tail) return [];
  const first = dayNumber(head.day);
  const span = dayNumber(tail.day) - first;
  return points.map((one) => (span === 0 ? 0.5 : (dayNumber(one.day) - first) / span));
}

const shortDay = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "2-digit" });

export function TrendChart({
  points,
  label,
  band,
  bandName = "Objetivo",
  valueName = "Valor",
  averageName = "Tendencia",
  format = (value) => value.toLocaleString("es-ES", { maximumFractionDigits: 1 }),
  formatDay = shortDay,
  marker = null,
  highlightName = "Destacado",
  flagOutside = true,
}: TrendChartProps) {
  const [hover, setHover] = React.useState<number | null>(null);
  const plot = React.useRef<HTMLDivElement>(null);

  if (points.length === 0) {
    return <p className="widget-note">Sin datos en este rango</p>;
  }

  const { min, max } = trendDomain(points, band);
  const y = (value: number) => H - ((value - min) / (max - min)) * H;
  const xs = trendX(points);
  const at = (index: number) => xs[index] ?? 0;
  const x = (index: number) => at(index) * W;
  const hasAverage = points.some((one) => one.average != null);
  const hasBand = band != null && (band.low != null || band.high != null);
  const hasHighlight = points.some((one) => one.highlight);
  const first = points[0];
  const last = points[points.length - 1];
  const markerAt =
    marker && first && last && marker.day > first.day && marker.day <= last.day
      ? (dayNumber(marker.day) - dayNumber(first.day)) / (dayNumber(last.day) - dayNumber(first.day))
      : null;
  const line = (pick: (one: TrendPoint) => number | null | undefined) =>
    points
      .map((one, index) => [index, pick(one)] as const)
      .filter(([, value]) => value != null)
      .map(([index, value]) => `${x(index)},${y(value as number)}`)
      .join(" ");
  const ticks = [max, (max + min) / 2, min];
  const edges = [0, Math.floor((points.length - 1) / 2), points.length - 1].filter(
    (value, index, all) => all.indexOf(value) === index,
  );

  const nearest = (clientX: number) => {
    const box = plot.current?.getBoundingClientRect();
    if (!box || box.width === 0) return null;
    const wanted = (clientX - box.left) / box.width;
    let best = 0;
    xs.forEach((value, index) => {
      if (Math.abs(value - wanted) < Math.abs(at(best) - wanted)) best = index;
    });
    return best;
  };

  const shown = hover === null ? null : (points[hover] ?? null);

  return (
    <figure className="series-chart trend-chart" aria-label={label}>
      <div
        className="series-chart-plot"
        ref={plot}
        onPointerMove={(event) => setHover(nearest(event.clientX))}
        onPointerLeave={() => setHover(null)}
      >
        <ul className="series-chart-ticks" aria-hidden="true">
          {ticks.map((value) => (
            <li key={value} style={{ top: `${(y(value) / H) * 100}%` }}>
              {format(value)}
            </li>
          ))}
        </ul>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
          {ticks.map((value) => (
            <line key={value} className="series-chart-grid" x1="0" x2={W} y1={y(value)} y2={y(value)} />
          ))}
          {hasBand && (
            <rect
              className="trend-chart-band"
              x="0"
              width={W}
              y={band?.high != null ? y(band.high) : 0}
              height={(band?.low != null ? y(band.low) : H) - (band?.high != null ? y(band.high) : 0)}
            />
          )}
          <polyline className={hasAverage ? "trend-chart-raw" : "trend-chart-line"} points={line((one) => one.value)} />
          {hasAverage && <polyline className="trend-chart-line" points={line((one) => one.average)} />}
          {markerAt !== null && (
            <line className="trend-chart-marker" x1={markerAt * W} x2={markerAt * W} y1="0" y2={H} />
          )}
          {hover !== null && (
            <line className="series-chart-cursor" x1={x(hover)} x2={x(hover)} y1="0" y2={H} />
          )}
        </svg>
        {points.length <= MAX_DOTS &&
          points.map((one, index) => (
            <span
              key={one.day + index}
              className="trend-chart-dot"
              data-highlight={one.highlight ? "" : undefined}
              data-out={
                flagOutside &&
                hasBand &&
                ((band?.low != null && one.value < band.low) || (band?.high != null && one.value > band.high))
                  ? ""
                  : undefined
              }
              style={{ left: `${at(index) * 100}%`, top: `${(y(one.value) / H) * 100}%` }}
              aria-hidden="true"
            />
          ))}
        {shown && hover !== null && (
          <div
            className="series-chart-tip"
            role="status"
            style={{ left: `${at(hover) * 100}%` }}
            data-side={at(hover) > 0.5 ? "left" : "right"}
          >
            <p className="series-chart-tip-title">{formatDay(shown.day)}</p>
            <p className="series-chart-tip-row">
              <span>{valueName}</span>
              <span className="series-chart-tip-value">{format(shown.value)}</span>
            </p>
            {shown.average != null && (
              <p className="series-chart-tip-row">
                <span>{averageName}</span>
                <span className="series-chart-tip-value">{format(shown.average)}</span>
              </p>
            )}
          </div>
        )}
      </div>
      <ul className="trend-chart-x" aria-hidden="true">
        {edges.map((index) => (
          <li
            key={index}
            style={{ left: `${at(index) * 100}%` }}
            data-edge={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"}
          >
            {formatDay(points[index]?.day ?? "")}
          </li>
        ))}
      </ul>
      {(hasAverage || hasBand || hasHighlight || markerAt !== null) && (
        <ul className="series-chart-legend">
          {hasAverage && (
            <li>
              <span className="trend-chart-key" data-key="line" aria-hidden="true" />
              {averageName}
            </li>
          )}
          <li>
            <span className="trend-chart-key" data-key={hasAverage ? "raw" : "line"} aria-hidden="true" />
            {valueName}
          </li>
          {hasBand && (
            <li>
              <span className="trend-chart-key" data-key="band" aria-hidden="true" />
              {bandName}
            </li>
          )}
          {hasHighlight && (
            <li>
              <span className="trend-chart-key" data-key="highlight" aria-hidden="true" />
              {highlightName}
            </li>
          )}
          {marker && markerAt !== null && (
            <li>
              <span className="trend-chart-key" data-key="marker" aria-hidden="true" />
              {marker.label}, {formatDay(marker.day)}
            </li>
          )}
        </ul>
      )}
      <details className="series-chart-table">
        <summary>Ver como tabla</summary>
        <div className="series-chart-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col">{valueName}</th>
                {hasAverage && <th scope="col">{averageName}</th>}
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((one, index) => (
                <tr key={one.day + index}>
                  <th scope="row">{formatDay(one.day)}</th>
                  <td>{format(one.value)}</td>
                  {hasAverage && <td>{one.average == null ? "" : format(one.average)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
