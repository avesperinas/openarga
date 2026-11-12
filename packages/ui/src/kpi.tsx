"use client";

import * as React from "react";

import { Sparkline } from "./charts";
import { compact, change, figureChars, percent } from "./format";
import { IconBadge, type IconName } from "./icons";
import { useAnimatedNumber } from "./motion";
import { spanOf } from "./sizes";
import { type Hue, useWidgetLayout, useWidgetSize } from "./Widget";

function Figure({ value, unit }: { value: number | string; unit?: string }) {
  const numeric = typeof value === "number" ? value : Number.NaN;
  const animated = useAnimatedNumber(Number.isFinite(numeric) ? numeric : 0);
  const shown = typeof value === "number" ? compact(animated) : value;

  return (
    <>
      {shown}
      {unit && <span className="kpi-unit">{unit}</span>}
    </>
  );
}

export interface WidgetKpiProps {
  value: number | string;
  unit?: string;
  detail?: string;
  icon?: IconName;
  hue?: Hue;
}

export function WidgetKpi({ value, unit, detail, icon, hue }: WidgetKpiProps) {
  return (
    <div className="kpi" data-with-icon={icon ? "" : undefined}>
      {icon && (
        <span className="kpi-icon">
          <IconBadge name={icon} hue={hue ?? 1} />
        </span>
      )}
      <p
        className="widget-value kpi-figure"
        data-text={typeof value === "string" && Number.isNaN(Number(value)) ? "" : undefined}
        style={{ "--chars": figureChars(value, unit) } as React.CSSProperties}
      >
        <Figure value={value} unit={unit} />
      </p>
      {detail && <p className="widget-detail">{detail}</p>}
    </div>
  );
}

export interface WidgetKpiDeltaProps extends WidgetKpiProps {
  previous: number;
  since?: string;
  goodWhen?: "up" | "down" | "neutral";
  series?: number[];
}

export function WidgetKpiDelta({
  value,
  previous,
  unit,
  detail,
  since,
  goodWhen = "up",
  series,
}: WidgetKpiDeltaProps) {
  const current = typeof value === "number" ? value : Number.NaN;
  const variation = Number.isFinite(current) ? change(current, previous) : null;
  const direction = variation === null ? 0 : Math.sign(variation);

  const label =
    variation === null
      ? previous === 0 && Number.isFinite(current) && current !== 0
        ? "sin dato anterior"
        : "sin cambio"
      : percent(variation);

  const tone =
    direction === 0 || goodWhen === "neutral"
      ? "neutral"
      : (direction > 0) === (goodWhen === "up")
        ? "good"
        : "bad";

  const trend = series && series.filter(Number.isFinite).length > 1;

  return (
    <div className="kpi" data-with-series={trend ? "" : undefined}>
      <div className="kpi-main">
        <p className="widget-value kpi-figure" style={{ "--chars": figureChars(value, unit) } as React.CSSProperties}>
          <Figure value={value} unit={unit} />
        </p>
        {detail && <p className="widget-detail">{detail}</p>}
        <p className="kpi-delta" data-tone={tone}>
          <span className="kpi-delta-pill">
            <span className="kpi-arrow" data-direction={direction} aria-hidden="true" />
            <span className="kpi-delta-value">{label}</span>
          </span>
          {since && <span className="kpi-delta-since">{since}</span>}
        </p>
      </div>
      {trend && (
        <div className="kpi-trend">
          <Sparkline series={series!} />
        </div>
      )}
    </div>
  );
}

export interface Stat {
  label: string;
  value: number | string;
  unit?: string;
}

export function WidgetStats({ items }: { items: Stat[] }) {
  const layout = useWidgetLayout();
  const size = useWidgetSize();
  const shown = items.slice(0, layout === "tiny" ? 1 : size === "2x1" ? 2 : layout === "narrow" ? 3 : 4);
  const [width] = spanOf(size);
  return (
    <ul className="stats" data-count={shown.length} data-wide={width >= 4 ? "" : undefined}>
      {shown.map((stat) => (
        <li key={stat.label} className="stat">
          <span className="stat-value">
            <Figure value={stat.value} unit={stat.unit} />
          </span>
          <span className="stat-label">{stat.label}</span>
        </li>
      ))}
    </ul>
  );
}
