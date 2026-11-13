"use client";

import * as React from "react";
import { locale } from "./regional";

export const SERIES_COLORS = 5;
export const OTHERS = "__others__";

export interface Series {
  key: string;
  name: string;
  values: number[];
}

export type SeriesKind = "bars" | "stacked" | "lines" | "area" | "step";

export function foldSeries(series: Series[], order: string[] = [], max = SERIES_COLORS): Series[] {
  const total = (one: Series) => one.values.reduce((sum, value) => sum + Math.abs(value), 0);
  const ranked = [...series].sort((a, b) => total(b) - total(a));
  const kept = ranked.slice(0, max);
  const rest = ranked.slice(max);
  const position = (key: string) => {
    const at = order.indexOf(key);
    return at === -1 ? order.length + ranked.findIndex((one) => one.key === key) : at;
  };
  kept.sort((a, b) => position(a.key) - position(b.key));
  if (rest.length === 0) return kept;
  const length = Math.max(...series.map((one) => one.values.length));
  const others = Array.from({ length }, (_, index) =>
    rest.reduce((sum, one) => sum + (one.values[index] ?? 0), 0),
  );
  return [...kept, { key: OTHERS, name: "Otros", values: others }];
}

export function niceCeiling(value: number): number {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((one) => one * power >= value) ?? 10;
  return step * power;
}

function closeCeiling(value: number): number {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((one) => one * power >= value) ?? 10;
  return step * power;
}

export function axisOf(series: Series[], kind: SeriesKind): { min: number; max: number } {
  const length = Math.max(0, ...series.map((one) => one.values.length));
  let top = 0;
  let bottom = 0;
  for (let index = 0; index < length; index++) {
    if (kind === "stacked" || kind === "area") {
      const up = series.reduce((sum, one) => sum + Math.max(0, one.values[index] ?? 0), 0);
      const down = series.reduce((sum, one) => sum + Math.min(0, one.values[index] ?? 0), 0);
      top = Math.max(top, up);
      bottom = Math.min(bottom, down);
    } else {
      for (const one of series) {
        const value = one.values[index] ?? 0;
        if (!Number.isFinite(value)) continue;
        top = Math.max(top, value);
        bottom = Math.min(bottom, value);
      }
    }
  }
  const ceiling = kind === "step" ? closeCeiling : niceCeiling;
  return { min: bottom < 0 ? -ceiling(-bottom) : 0, max: ceiling(top) };
}

export function labelStep(count: number, room = 8): number {
  return Math.max(1, Math.ceil(count / room));
}

const W = 100;
const H = 60;

function shownValue(value: number | undefined, format: (value: number) => string): string {
  return value === undefined || !Number.isFinite(value) ? "—" : format(value);
}

export function stepPath(values: number[], step: number, y: (value: number) => number): string {
  let path = "";
  let open = false;
  values.forEach((value, index) => {
    if (!Number.isFinite(value)) {
      open = false;
      return;
    }
    const left = index * step;
    const right = (index + 1) * step;
    path += open ? ` V${y(value)} H${right}` : `${path ? " " : ""}M${left},${y(value)} H${right}`;
    open = true;
  });
  return path;
}

export interface SeriesChartProps {
  labels: string[];
  series: Series[];
  kind?: SeriesKind;
  format?: (value: number) => string;
  axisFormat?: (value: number) => string;
  label: string;
  order?: string[];
  overlay?: Series;
  palette?: "stages" | "zones";
}

export function SeriesChart({
  labels,
  series,
  kind = "bars",
  format = (value) => value.toLocaleString(locale()),
  label,
  order = [],
  axisFormat,
  overlay,
  palette,
}: SeriesChartProps) {
  const [hover, setHover] = React.useState<number | null>(null);
  const shown = foldSeries(series, order);
  const count = labels.length;
  const axis = axisOf(shown, kind);
  const known = overlay ? { ...overlay, values: overlay.values.filter(Number.isFinite) } : undefined;
  const min = known && known.values.length > 0 ? Math.min(axis.min, axisOf([known], "lines").min) : axis.min;
  const max = known && known.values.length > 0 ? Math.max(axis.max, axisOf([known], "lines").max) : axis.max;
  const y = (value: number) => H - ((value - min) / (max - min || 1)) * H;
  const step = W / Math.max(1, count);
  const colour = (key: string) =>
    key === OTHERS ? "others" : String(shown.findIndex((one) => one.key === key));
  const every = labelStep(count);
  const ticks = (min < 0 ? [max, 0, min] : [max, (max + min) / 2, min]).filter(
    (value, index, all) => all.indexOf(value) === index,
  );

  if (count === 0 || shown.length === 0) {
    return <p className="widget-note">Sin datos en este rango</p>;
  }

  return (
    <figure className="series-chart" aria-label={label} data-palette={palette}>
      <div className="series-chart-plot">
        <ul className="series-chart-ticks" aria-hidden="true">
          {ticks.map((value) => (
            <li key={value} style={{ top: `${(y(value) / H) * 100}%` }}>
              {(axisFormat ?? format)(value)}
            </li>
          ))}
        </ul>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label}>
          {ticks.map((value) => (
            <line key={value} className="series-chart-grid" x1="0" x2={W} y1={y(value)} y2={y(value)} />
          ))}
          {kind === "lines" &&
            shown.map((one) => (
              <polyline
                key={one.key}
                className="series-chart-line"
                data-series={colour(one.key)}
                points={one.values.map((value, index) => `${(index + 0.5) * step},${y(value)}`).join(" ")}
              />
            ))}
          {kind === "step" &&
            shown.map((one) => (
              <path
                key={one.key}
                className="series-chart-line"
                data-series={colour(one.key)}
                d={stepPath(one.values, step, y)}
              />
            ))}
          {kind === "bars" &&
            shown.map((one, position) => {
              const width = (step * 0.72) / shown.length;
              return one.values.map((value, index) => (
                <rect
                  key={`${one.key}-${index}`}
                  className="series-chart-bar"
                  data-series={colour(one.key)}
                  x={index * step + step * 0.14 + position * width}
                  width={width}
                  y={Math.min(y(value), y(0))}
                  height={Math.abs(y(value) - y(0))}
                />
              ));
            })}
          {kind === "stacked" &&
            Array.from({ length: count }, (_, index) => {
              let up = 0;
              let down = 0;
              return shown.map((one) => {
                const value = one.values[index] ?? 0;
                const from = value >= 0 ? up : down;
                const to = from + value;
                if (value >= 0) up = to;
                else down = to;
                return (
                  <rect
                    key={`${one.key}-${index}`}
                    className="series-chart-bar"
                    data-series={colour(one.key)}
                    x={index * step + step * 0.18}
                    width={step * 0.64}
                    y={Math.min(y(from), y(to))}
                    height={Math.abs(y(to) - y(from))}
                  />
                );
              });
            })}
          {kind === "area" &&
            (() => {
              const at = (index: number) => (index + 0.5) * step;
              let below = Array.from({ length: count }, () => 0);
              return shown.map((one) => {
                const above = below.map((value, index) => value + Math.max(0, one.values[index] ?? 0));
                const top = above.map((value, index) => `${at(index)},${y(value)}`);
                const bottom = below.map((value, index) => `${at(index)},${y(value)}`).reverse();
                below = above;
                return (
                  <polygon
                    key={one.key}
                    className="series-chart-area"
                    data-series={colour(one.key)}
                    points={[...top, ...bottom].join(" ")}
                  />
                );
              });
            })()}
          {overlay && (
            <polyline
              className="series-chart-overlay"
              points={overlay.values
                .map((value, index) => (Number.isFinite(value) ? `${(index + 0.5) * step},${y(value)}` : null))
                .filter(Boolean)
                .join(" ")}
            />
          )}
          {min < 0 && <line className="series-chart-zero" x1="0" x2={W} y1={y(0)} y2={y(0)} />}
          {hover !== null && (
            <line className="series-chart-cursor" x1={(hover + 0.5) * step} x2={(hover + 0.5) * step} y1="0" y2={H} />
          )}
        </svg>
        <div className="series-chart-hits">
          {labels.map((text, index) => (
            <button
              key={text + index}
              type="button"
              aria-label={`${text}: ${[...shown, ...(overlay ? [overlay] : [])]
                .map((one) => `${one.name} ${shownValue(one.values[index], format)}`)
                .join(", ")}`}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(index)}
              onBlur={() => setHover(null)}
            />
          ))}
        </div>
        {hover !== null && (
          <div
            className="series-chart-tip"
            role="status"
            style={{ left: `${((hover + 0.5) / count) * 100}%` }}
            data-side={hover > count / 2 ? "left" : "right"}
          >
            <p className="series-chart-tip-title">{labels[hover]}</p>
            {shown.map((one) => (
              <p key={one.key} className="series-chart-tip-row">
                <span className="series-chart-swatch" data-series={colour(one.key)} aria-hidden="true" />
                <span>{one.name}</span>
                <span className="series-chart-tip-value">{shownValue(one.values[hover], format)}</span>
              </p>
            ))}
            {overlay && (
              <p className="series-chart-tip-row">
                <span className="series-chart-swatch" data-overlay="" aria-hidden="true" />
                <span>{overlay.name}</span>
                <span className="series-chart-tip-value">
                  {Number.isFinite(overlay.values[hover] ?? Number.NaN) ? format(overlay.values[hover]!) : "—"}
                </span>
              </p>
            )}
          </div>
        )}
      </div>
      <ul className="chart-labels series-chart-x" aria-hidden="true">
        {labels.map((text, index) => (
          <li key={text + index}>{index % every === 0 ? text : ""}</li>
        ))}
      </ul>
      {(shown.length > 1 || overlay) && (
        <ul className="series-chart-legend">
          {shown.map((one) => (
            <li key={one.key}>
              <span className="series-chart-swatch" data-series={colour(one.key)} aria-hidden="true" />
              {one.name}
            </li>
          ))}
          {overlay && (
            <li>
              <span className="series-chart-swatch" data-overlay="" aria-hidden="true" />
              {overlay.name}
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
                {shown.map((one) => (
                  <th key={one.key} scope="col">
                    {one.name}
                  </th>
                ))}
                {overlay && <th scope="col">{overlay.name}</th>}
              </tr>
            </thead>
            <tbody>
              {labels.map((text, index) => (
                <tr key={text + index}>
                  <th scope="row">{text}</th>
                  {shown.map((one) => (
                    <td key={one.key}>{shownValue(one.values[index], format)}</td>
                  ))}
                  {overlay && <td>{Number.isFinite(overlay.values[index] ?? Number.NaN) ? format(overlay.values[index]!) : "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

export function FilterBar({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="filter-bar" role="group" aria-label={label}>
      {children}
    </div>
  );
}
