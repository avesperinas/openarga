"use client";

import * as React from "react";

import { Icon } from "./icons";

export type WeekDayState = "met" | "missed" | "today" | "future" | "before";

export interface WeekDotsProps {
  days: { day: string; state: WeekDayState; kind?: string; today?: boolean }[];
  label: string;
  size?: "regular" | "large";
}

const LETTERS = ["L", "M", "X", "J", "V", "S", "D"];

export function WeekDots({ days, label, size = "regular" }: WeekDotsProps) {
  const large = size === "large";
  return (
    <span className="goal-week" role="img" aria-label={label} data-size={large ? "large" : undefined}>
      {days.map(({ day, state, kind, today }, index) => (
        <span
          key={day}
          className="goal-week-day"
          data-state={state}
          data-kind={kind}
          data-today={today || state === "today" || undefined}
        >
          <span className="goal-week-letter" aria-hidden="true">
            {LETTERS[index] ?? ""}
          </span>
          <span className="goal-week-mark" aria-hidden="true">
            {large && state === "met" ? "✓" : null}
          </span>
        </span>
      ))}
    </span>
  );
}

export type GoalTone = "positive" | "warning" | "negative" | "neutral";

export interface GoalRowProps {
  title: string;
  subtitle?: string;
  hue?: number | null;
  tone?: GoalTone;
  status?: string;
  figure?: string;
  against?: string;
  progress?: number | null;
  expected?: number | null;
  week?: WeekDotsProps["days"];
  weekLabel?: string;
  check?: { checked: boolean; label: string; onClick: () => void };
  onOpen?: () => void;
}

const clamp = (value: number) => Math.max(0, Math.min(1, value));

export function GoalRow({
  title,
  subtitle,
  hue,
  tone = "neutral",
  status,
  figure,
  against,
  progress,
  expected,
  week,
  weekLabel,
  check,
  onOpen,
}: GoalRowProps) {
  const body = (
    <>
      <span className="goal-row-head">
        {hue ? <span className="list-row-dot" data-hue={hue} aria-hidden="true" /> : null}
        <span className="goal-row-title">{title}</span>
        {status && <span className="goal-row-status">{status}</span>}
      </span>
      {subtitle && <span className="goal-row-subtitle">{subtitle}</span>}
      {(figure || against) && (
        <span className="goal-row-figure">
          {figure && <strong>{figure}</strong>}
          {against && <span>{against}</span>}
        </span>
      )}
      {progress !== undefined && progress !== null && (
        <span
          className="goal-row-track"
          aria-hidden="true"
          style={
            {
              "--filled": clamp(progress),
              "--pace": expected === undefined || expected === null ? undefined : clamp(expected),
            } as React.CSSProperties
          }
        >
          <span className="goal-row-fill" />
          {expected !== undefined && expected !== null && <span className="goal-row-pace" />}
        </span>
      )}
      {week && <WeekDots days={week} label={weekLabel ?? title} />}
    </>
  );
  return (
    <div className="goal-row" data-tone={tone}>
      {onOpen ? (
        <button type="button" className="goal-row-body" onClick={onOpen}>
          {body}
        </button>
      ) : (
        <div className="goal-row-body">{body}</div>
      )}
      {check && (
        <button
          type="button"
          className="goal-row-check"
          aria-pressed={check.checked}
          aria-label={check.label}
          onClick={check.onClick}
        >
          <Icon name="done" />
        </button>
      )}
    </div>
  );
}
