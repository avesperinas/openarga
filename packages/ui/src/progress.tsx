"use client";

import * as React from "react";

import { figureChars, compact, plain, ratio } from "./format";
import { Icon } from "./icons";
import { useAnimatedNumber } from "./motion";
import { fitsUncertaintyLine, isCompact, layoutOf } from "./sizes";
import { useWidgetSize } from "./Widget";

export interface WidgetProgressProps {
  value: number;
  target: number;
  unit?: string;
  label?: string;
  expected?: number;
  goodWhen?: "up" | "down";
}

const paceOf = (expected: number | undefined, target: number): number | undefined =>
  expected === undefined || !Number.isFinite(expected) || target <= 0
    ? undefined
    : ratio(expected, target);

export function WidgetProgress({
  value,
  target,
  unit,
  label,
  expected,
  goodWhen = "up",
}: WidgetProgressProps) {
  const animated = useAnimatedNumber(Number.isFinite(value) ? value : 0);
  const filled = ratio(animated, target);
  const ceiling = goodWhen === "down";
  const done = !ceiling && value >= target && target > 0;
  const pace = paceOf(expected, target);
  const standing = !ceiling
    ? undefined
    : value > target
      ? "over"
      : expected !== undefined && value > expected
        ? "ahead"
        : "fine";

  return (
    <div className="progress" data-done={done || undefined} data-standing={standing}>
      <p className="widget-value kpi-figure" style={{ "--chars": figureChars(value, unit) } as React.CSSProperties}>
        {compact(animated)}
        {unit && <span className="kpi-unit">{unit}</span>}
      </p>
      {label && <p className="widget-detail">{label}</p>}
      <div className="progress-foot">
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={Math.round(ratio(value, target) * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ "--filled": filled, "--pace": pace } as React.CSSProperties}
      >
        <span className="progress-fill" data-done={done || undefined} />
        {pace !== undefined && <span className="progress-pace" aria-hidden="true" />}
      </div>
      <p className="progress-scale">
        <span className="progress-percent">
          {done
            ? "Objetivo cumplido"
            : standing === "over"
              ? `${plain(value - target)}${unit ? ` ${unit}` : ""} de más`
              : `${Math.round(ratio(value, target) * 100)} %`}
        </span>
        <span>{`${plain(target)}${unit ? ` ${unit}` : ""}`}</span>
      </p>
      </div>
    </div>
  );
}

export interface WidgetRingProps extends WidgetProgressProps {
  show?: "value" | "percent";
}

const R = 40;
const CIRCUMFERENCE = 2 * Math.PI * R;

export function WidgetRing({ value, target, unit, label, show = "value", expected }: WidgetRingProps) {
  const animated = useAnimatedNumber(Number.isFinite(value) ? value : 0);
  const filled = ratio(animated, target);
  const size = useWidgetSize();
  const pace = paceOf(expected, target);
  const done = value >= target && target > 0;
  const tally = `${plain(value)} de ${plain(target)}`;

  return (
    <div className="ring" data-done={done || undefined}>
      <div className="ring-canvas">
        <svg
          viewBox="0 0 100 100"
          role="img"
          aria-label={`${label ?? "Avance"}: ${tally}${done ? ", objetivo cumplido" : ""}`}
        >
          <circle className="ring-track" cx="50" cy="50" r={R} />
          <circle
            className="ring-fill"
            cx="50"
            cy="50"
            r={R}
            style={
              {
                strokeDasharray: CIRCUMFERENCE,
                strokeDashoffset: CIRCUMFERENCE * (1 - filled),
              } as React.CSSProperties
            }
          />
          {pace !== undefined && !done && (
            <line
              className="ring-pace"
              x1={50 + (R - 8) * Math.cos(2 * Math.PI * pace)}
              y1={50 + (R - 8) * Math.sin(2 * Math.PI * pace)}
              x2={50 + (R + 8) * Math.cos(2 * Math.PI * pace)}
              y2={50 + (R + 8) * Math.sin(2 * Math.PI * pace)}
            />
          )}
        </svg>
        {done ? (
          <span className="ring-check" aria-hidden="true">
            <Icon name="done" />
          </span>
        ) : (
          <p className="ring-figure">
            {show === "percent" ? (
              `${Math.round(ratio(animated, target) * 100)}%`
            ) : (
              <>
                {compact(animated)}
                {unit && <span className="kpi-unit">{unit}</span>}
              </>
            )}
          </p>
        )}
      </div>
      {(!isCompact(size) || layoutOf(size) === "strip") &&
        (done ? (
          <p className="widget-detail ring-label ring-done">
            {fitsUncertaintyLine(size) ? `Objetivo cumplido · ${tally}` : `Cumplido · ${tally}`}
          </p>
        ) : (
          label && <p className="widget-detail ring-label">{label}</p>
        ))}
    </div>
  );
}

export interface WidgetStreakProps {
  current: number;
  best?: number;
  days?: boolean[];
  label?: string;
}

export function WidgetStreak({ current, best, days, label }: WidgetStreakProps) {
  const animated = useAnimatedNumber(Number.isFinite(current) ? current : 0);
  const rounded = Math.round(animated);

  return (
    <div className="streak">
      <p className="widget-value streak-figure">
        {rounded}
        <span className="kpi-unit">{rounded === 1 ? "día" : "días"}</span>
      </p>
      {days && days.length > 0 && (
        <ul className="streak-days" aria-hidden="true">
          {days.slice(-14).map((done, index) => (
            <li
              key={index}
              className="streak-day"
              data-done={done || undefined}
              style={{ "--cell-index": index } as React.CSSProperties}
            />
          ))}
        </ul>
      )}
      <p className="widget-detail">
        {label ?? "seguidos"}
        {best !== undefined && best > 0 && ` · récord ${plain(best)}`}
      </p>
    </div>
  );
}
