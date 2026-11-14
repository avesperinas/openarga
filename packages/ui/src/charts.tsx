"use client";

import * as React from "react";

import { figureChars, compact } from "./format";
import { useAnimatedNumber } from "./motion";
import { spanOf } from "./sizes";
import { useCardSize, useWidgetLayout } from "./Widget";
import { say } from "./words";

const W = 100;
const H = 40;

const PAD = 3;

interface Scale {
  min: number;
  max: number;
}

const scaleOf = (series: number[]): Scale => {
  const clean = series.filter(Number.isFinite);
  if (clean.length === 0) return { min: 0, max: 1 };
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  return min === max ? { min: min - 1, max: max + 1 } : { min, max };
};

const project = (series: number[], { min, max }: Scale): [number, number][] =>
  series.map((value, index) => [
    series.length === 1 ? W / 2 : (index / (series.length - 1)) * W,
    H - PAD - ((value - min) / (max - min)) * (H - PAD * 2),
  ]);

function curve(points: [number, number][]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0]![0]} ${points[0]![1]}`;

  const at = (index: number) => points[Math.max(0, Math.min(points.length - 1, index))]!;
  let path = `M ${at(0)[0]} ${at(0)[1]}`;

  for (let i = 0; i < points.length - 1; i++) {
    const [x0, y0] = at(i - 1);
    const [x1, y1] = at(i);
    const [x2, y2] = at(i + 1);
    const [x3, y3] = at(i + 2);
    const c1x = x1 + (x2 - x0) / 6;
    const c1y = y1 + (y2 - y0) / 6;
    const c2x = x2 - (x3 - x1) / 6;
    const c2y = y2 - (y3 - y1) / 6;
    path += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  }
  return path;
}

function Headline({
  value,
  unit,
  detail,
}: {
  value?: number | string;
  unit?: string;
  detail?: string;
}) {
  const numeric = typeof value === "number" ? value : Number.NaN;
  const animated = useAnimatedNumber(Number.isFinite(numeric) ? numeric : 0);
  if (value === undefined) return detail ? <p className="widget-detail">{detail}</p> : null;

  return (
    <div className="chart-headline">
      <p className="widget-value kpi-figure" style={{ "--chars": figureChars(value, unit) } as React.CSSProperties}>
        {typeof value === "number" ? compact(animated) : value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </p>
      {detail && <p className="widget-detail chart-headline-detail">{detail}</p>}
    </div>
  );
}

export function Sparkline({
  series,
  label,
  marks = [],
}: {
  series: (number | null)[];
  label?: string;
  marks?: number[];
}) {
  const clean = series.filter((value): value is number => value !== null && Number.isFinite(value));
  if (clean.length < 2) return null;
  const scale = scaleOf(clean);
  const x = (index: number) => (series.length === 1 ? W / 2 : (index / (series.length - 1)) * W);
  const runs: [number, number][][] = [];
  let run: [number, number][] = [];
  series.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) {
      if (run.length > 0) runs.push(run);
      run = [];
      return;
    }
    run.push([x(index), H - PAD - ((value - scale.min) / (scale.max - scale.min)) * (H - PAD * 2)]);
  });
  if (run.length > 0) runs.push(run);
  const last = runs.at(-1)!.at(-1)!;
  const joined = runs.length === 1;
  const line = runs.map((points) => (points.length === 1 ? `M ${points[0]![0]} ${points[0]![1]} h 0.01` : curve(points))).join(" ");
  return (
    <svg
      className="sparkline"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label ?? say("chart.evolution", { count: clean.length })}
    >
      {joined && <path className="chart-area" d={`${line} L ${runs[0]!.at(-1)![0]} ${H} L ${runs[0]![0]![0]} ${H} Z`} />}
      {marks.map((index) => (
        <line key={index} className="sparkline-mark" x1={x(index)} x2={x(index)} y1={0} y2={H} vectorEffect="non-scaling-stroke" />
      ))}
      <path className="chart-line" d={line} vectorEffect="non-scaling-stroke" />
      <circle className="chart-head" cx={last[0]} cy={last[1]} r="2.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export interface WidgetChartProps {
  series: number[];
  value?: number | string;
  unit?: string;
  detail?: string;
  fill?: boolean;
}

export function WidgetChart({ series, value, unit, detail, fill = true }: WidgetChartProps) {
  const clean = series.filter(Number.isFinite);
  const points = project(clean, scaleOf(clean));
  const line = curve(points);
  const last = points[points.length - 1];

  return (
    <div className="chart">
      <Headline value={value} unit={unit} detail={detail} />
      {clean.length === 0 ? (
        <p className="widget-note">{say("chart.no_series")}</p>
      ) : (
        <div className="chart-plot">
        <svg
          className="chart-canvas"
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={say("chart.evolution", { count: clean.length })}
        >
          {fill && line && (
            <path className="chart-area" d={`${line} L ${W} ${H} L 0 ${H} Z`} />
          )}
          <path className="chart-line" d={line} vectorEffect="non-scaling-stroke" />
          {last && (
            <circle className="chart-head" cx={last[0]} cy={last[1]} r="2.5" vectorEffect="non-scaling-stroke" />
          )}
        </svg>
        </div>
      )}
    </div>
  );
}

export interface WidgetBarsProps {
  series: number[];
  labels?: string[];
  value?: number | string;
  unit?: string;
  detail?: string;
  highlight?: number;
}

export function WidgetBars({
  series,
  labels,
  value,
  unit,
  detail,
  highlight,
}: WidgetBarsProps) {
  const clean = series.filter(Number.isFinite);
  const top = Math.max(...clean, 0) || 1;
  const card = useCardSize();
  const sparse = card !== null && (labels?.length ?? 0) > spanOf(card)[0] * 3;
  const step = W / Math.max(1, clean.length);
  const width = step * 0.62;

  return (
    <div className="chart">
      <Headline value={value} unit={unit} detail={detail} />
      {clean.length === 0 ? (
        <p className="widget-note">{say("chart.no_series")}</p>
      ) : (
        <div className="chart-plot">
          <svg
            className="chart-canvas"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${clean.length} periodos`}
          >
            {clean.map((entry, index) => (
              <rect
                key={index}
                className="chart-bar"
                data-highlight={index === highlight || undefined}
                x={index * step + (step - width) / 2}
                y="0"
                width={width}
                height={H}
                rx="1.5"
                style={
                  {
                    "--bar": Math.max(entry / top, 0.02),
                    "--bar-index": index,
                  } as React.CSSProperties
                }
              />
            ))}
          </svg>
          {labels && labels.length === clean.length && (
            <ul className="chart-labels" aria-hidden="true">
              {labels.map((label, index) => {
                const shown =
                  !sparse || index === 0 || index === labels.length - 1 || index === highlight;
                return (
                  <li key={index} data-highlight={index === highlight || undefined}>
                    {shown ? label : ""}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export interface WidgetHeatmapProps {
  values: number[];
  columns?: number;
  detail?: string;
}

export function WidgetHeatmap({ values: all, columns: given = 7, detail }: WidgetHeatmapProps) {
  const top = Math.max(...all.filter(Number.isFinite), 0) || 1;
  const layout = useWidgetLayout();
  const size = useCardSize();
  const values =
    layout === "strip"
      ? all.slice(size === "2x1" ? -10 : -21)
      : layout === "tiny"
        ? all.slice(-28)
        : layout === "narrow"
          ? all.slice(-42)
          : layout === "tall"
            ? all.slice(-7 * 18)
            : all;
  const columns =
    layout === "strip" ? values.length : ["tiny", "narrow", "tall"].includes(layout) ? 7 : given;

  return (
    <div className="heatmap-wrap">
      {detail && <p className="widget-detail">{detail}</p>}
      <div className="heatmap-frame">
      <ul
        className="heatmap"
        style={
          {
            "--heatmap-columns": columns,
            "--heatmap-rows": Math.max(1, Math.ceil(values.length / columns)),
          } as React.CSSProperties
        }
        aria-label={say("chart.consistency", { count: values.length })}
      >
        {values.map((entry, index) => (
          <li
            key={index}
            className="heatmap-cell"
            data-level={entry <= 0 ? 0 : Math.min(4, Math.ceil((entry / top) * 4))}
            style={{ "--cell-index": index } as React.CSSProperties}
          />
        ))}
      </ul>
      </div>
    </div>
  );
}
