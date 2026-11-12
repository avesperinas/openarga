"use client";

import * as React from "react";

import { Icon } from "./icons";
import { StatRow, StatTile } from "./reading";
import { Hint } from "./screen";

const MINUTE = 60_000;

const pad = (value: number) => String(value).padStart(2, "0");

export function clockOf(iso: string | number): string {
  const moment = new Date(iso);
  return `${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
}

export function minutesText(minutes: number): string {
  const whole = Math.round(minutes);
  if (whole < 60) return `${whole} min`;
  return `${Math.floor(whole / 60)} h ${pad(whole % 60)}`;
}

export function InfoButton({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="info-button"
      aria-label={open ? `Cerrar qué es ${label.toLowerCase()}` : `Qué es ${label.toLowerCase()}`}
      aria-expanded={open}
      onClick={onToggle}
    >
      <Icon name={open ? "close" : "info"} />
    </button>
  );
}

export function InfoHeading({ children, info }: { children: string; info?: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="info-heading">
      <div className="info-heading-row">
        <h2 className="info-heading-title">{children}</h2>
        {info && <InfoButton label={children} open={open} onToggle={() => setOpen(!open)} />}
      </div>
      {open && info && <div className="info-why">{info}</div>}
    </div>
  );
}

export interface KeyFigure {
  label: string;
  value: string;
  foot?: string;
  tone?: "neutral" | "warning" | "positive" | "negative";
  info?: React.ReactNode;
  onOpen?: () => void;
}

export function KeyFigures({ items, label }: { items: KeyFigure[]; label: string }) {
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <dl className="key-figures" aria-label={label}>
      {items.map((one) => (
        <div key={one.label} className="key-figure" data-tone={one.tone}>
          <dt>
            {one.label}
            {one.info && (
              <InfoButton label={one.label} open={open === one.label} onToggle={() => setOpen(open === one.label ? null : one.label)} />
            )}
          </dt>
          <dd>
            {one.onOpen ? (
              <button type="button" className="key-figure-open" onClick={one.onOpen} aria-label={`${one.label}: ${one.value}. Ver el detalle`}>
                <span className="key-figure-text">
                  <span className="key-figure-value">{one.value}</span>
                  {one.foot && <span className="key-figure-foot">{one.foot}</span>}
                </span>
                <Icon name="chevron-right" />
              </button>
            ) : (
              <>
                <span className="key-figure-value">{one.value}</span>
                {one.foot && <span className="key-figure-foot">{one.foot}</span>}
              </>
            )}
          </dd>
          {open === one.label && <div className="info-why">{one.info}</div>}
        </div>
      ))}
    </dl>
  );
}

export function BatteryLine({ name, percent, detail }: { name: string; percent: number; detail?: string }) {
  const low = percent <= 20;
  return (
    <div className="battery-line" data-low={low || undefined} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label={`Batería de ${name}`}>
      <span className="battery-line-text">
        <span>{name}</span>
        <span className="battery-line-value">
          {percent} %{detail ? ` · ${detail}` : ""}
        </span>
      </span>
      <span className="battery-line-track" aria-hidden="true">
        <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
      </span>
    </div>
  );
}

export type Quality = "excellent" | "good" | "fair" | "poor";

export const QUALITY_NAMES: Record<Quality, string> = {
  excellent: "Excelente",
  good: "Buena",
  fair: "Regular",
  poor: "Mala",
};

export interface HealthRingProps {
  value: number;
  target: number;
  display: string;
  label: string;
  caption?: string;
  quality?: Quality;
  size?: "m" | "l";
  info?: React.ReactNode;
  wideOnly?: boolean;
  mark?: number;
}

const R = 42;
const CIRCLE = 2 * Math.PI * R;

export function ringMark(share: number, radius = R, length = 9): { x1: number; y1: number; x2: number; y2: number } {
  const angle = Math.max(0, Math.min(1, share)) * 2 * Math.PI;
  const inner = radius - length / 2 - 2;
  const outer = radius + length / 2 + 2;
  const at = (r: number) => ({ x: 50 + r * Math.sin(angle), y: 50 - r * Math.cos(angle) });
  const a = at(inner);
  const b = at(outer);
  const round = (n: number) => Math.round(n * 100) / 100;
  return { x1: round(a.x), y1: round(a.y), x2: round(b.x), y2: round(b.y) };
}

export function RingArc({ filled, mark }: { filled: number; mark?: number }) {
  return (
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <g className="health-ring-turn">
        <circle className="health-ring-track" cx="50" cy="50" r={R} />
        <circle
          className="health-ring-fill"
          cx="50"
          cy="50"
          r={R}
          strokeDasharray={CIRCLE}
          strokeDashoffset={CIRCLE * (1 - Math.max(0, Math.min(1, filled)))}
        />
      </g>
      {mark !== undefined && <line className="health-ring-mark" {...ringMark(mark)} />}
    </svg>
  );
}

export function HealthRing({ value, target, display, label, caption, quality, size = "m", info, wideOnly, mark }: HealthRingProps) {
  const filled = target > 0 ? Math.max(0, Math.min(1, value / target)) : 0;
  const [open, setOpen] = React.useState(false);
  return (
    <figure
      className="health-ring"
      data-size={size}
      data-quality={quality}
      data-wide-only={wideOnly || undefined}
      aria-label={`${label}: ${display}${caption ? `, ${caption}` : ""}`}
    >
      <div className="health-ring-canvas">
        <RingArc filled={filled} mark={mark} />
        <p className="health-ring-figure">
          <span className="health-ring-value">{display}</span>
          {caption && <span className="health-ring-caption">{caption}</span>}
        </p>
      </div>
      <figcaption className="health-ring-label">
        {label}
        {info && <InfoButton label={label} open={open} onToggle={() => setOpen(!open)} />}
      </figcaption>
      {open && info && <div className="info-why">{info}</div>}
    </figure>
  );
}

export type SleepStage = "awake" | "rem" | "light" | "deep";

export const STAGE_NAMES: Record<SleepStage, string> = {
  awake: "Despierto",
  rem: "REM",
  light: "Ligero",
  deep: "Profundo",
};

export const STAGE_LANES: SleepStage[] = ["awake", "rem", "light", "deep"];

export interface StageSegment {
  start: string;
  end: string;
  stage: SleepStage | "asleep" | "restless";
}

export interface HypnogramBar {
  x: number;
  width: number;
  lane: number;
  stage: SleepStage;
  start: string;
  end: string;
}

export function laneStage(stage: StageSegment["stage"]): SleepStage {
  if (stage === "asleep") return "light";
  if (stage === "restless") return "awake";
  return stage;
}

export function hypnogramBars(segments: StageSegment[], start: string, end: string): HypnogramBar[] {
  const first = Date.parse(start);
  const span = Date.parse(end) - first;
  if (!(span > 0)) return [];
  return segments
    .map((one) => {
      const from = Math.max(0, (Date.parse(one.start) - first) / span);
      const to = Math.min(1, (Date.parse(one.end) - first) / span);
      const stage = laneStage(one.stage);
      return { x: from, width: to - from, lane: STAGE_LANES.indexOf(stage), stage, start: one.start, end: one.end };
    })
    .filter((one) => one.width > 0);
}

export function hourTicks(start: string, end: string, every = 2): { x: number; label: string }[] {
  const first = Date.parse(start);
  const last = Date.parse(end);
  const span = last - first;
  if (!(span > 0)) return [];
  const moment = new Date(first);
  moment.setMinutes(0, 0, 0);
  moment.setHours(moment.getHours() + 1);
  const ticks = [];
  while (moment.getTime() < last) {
    if (moment.getHours() % every === 0) {
      ticks.push({ x: (moment.getTime() - first) / span, label: `${pad(moment.getHours())}:00` });
    }
    moment.setHours(moment.getHours() + 1);
  }
  return ticks;
}

export interface HypnogramProps {
  segments: StageSegment[];
  start: string;
  end: string;
  pulse?: { at: string; bpm: number }[];
  label: string;
}

const LANE_H = 15;
const HYPNO_H = LANE_H * STAGE_LANES.length;

export function Hypnogram({ segments, start, end, pulse = [], label }: HypnogramProps) {
  const bars = hypnogramBars(segments, start, end);
  const ticks = hourTicks(start, end);
  const [hover, setHover] = React.useState<HypnogramBar | null>(null);
  const first = Date.parse(start);
  const span = Date.parse(end) - first;
  const beats = pulse.filter((one) => Date.parse(one.at) >= first && Date.parse(one.at) <= first + span);
  const low = Math.min(...beats.map((one) => one.bpm));
  const high = Math.max(...beats.map((one) => one.bpm));
  const room = Math.max(10, high - low);
  const line = beats
    .map((one) => {
      const x = ((Date.parse(one.at) - first) / span) * 100;
      const y = 4 + (1 - (one.bpm - low) / room) * (HYPNO_H - 8);
      return `${x},${y}`;
    })
    .join(" ");

  if (bars.length === 0) return <p className="widget-note">Esta noche llegó sin fases.</p>;

  return (
    <figure className="hypnogram" aria-label={label}>
      <div className="hypnogram-plot">
        <ul className="hypnogram-lanes" aria-hidden="true">
          {STAGE_LANES.map((stage) => (
            <li key={stage} data-stage={stage}>
              {STAGE_NAMES[stage]}
            </li>
          ))}
        </ul>
        <div className="hypnogram-canvas" onPointerLeave={() => setHover(null)}>
          <svg viewBox={`0 0 100 ${HYPNO_H}`} preserveAspectRatio="none" role="img" aria-label={label}>
            {STAGE_LANES.map((stage, lane) => (
              <rect key={stage} className="hypnogram-lane" x="0" y={lane * LANE_H} width="100" height={LANE_H} data-odd={lane % 2 || undefined} />
            ))}
            {bars.slice(1).map((bar, index) => {
              const before = bars[index];
              if (!before || Math.abs(before.x + before.width - bar.x) > 0.002) return null;
              const top = Math.min(before.lane, bar.lane) * LANE_H + LANE_H / 2;
              const bottom = Math.max(before.lane, bar.lane) * LANE_H + LANE_H / 2;
              return <line key={`step-${bar.start}`} className="hypnogram-step" x1={bar.x * 100} x2={bar.x * 100} y1={top} y2={bottom} />;
            })}
            {bars.map((bar) => (
              <rect
                key={bar.start}
                className="hypnogram-bar"
                data-stage={bar.stage}
                x={bar.x * 100}
                width={Math.max(0.15, bar.width * 100)}
                y={bar.lane * LANE_H + 2}
                height={LANE_H - 4}
                rx="1"
                onPointerEnter={() => setHover(bar)}
              />
            ))}
            {beats.length > 1 && <polyline className="hypnogram-pulse" points={line} />}
          </svg>
          {hover && (
            <div className="series-chart-tip" role="status" style={{ left: `${(hover.x + hover.width / 2) * 100}%` }} data-side={hover.x > 0.5 ? "left" : "right"}>
              <p className="series-chart-tip-title">{STAGE_NAMES[hover.stage]}</p>
              <p className="series-chart-tip-row">
                <span>
                  {clockOf(hover.start)} – {clockOf(hover.end)}
                </span>
                <span className="series-chart-tip-value">{minutesText((Date.parse(hover.end) - Date.parse(hover.start)) / MINUTE)}</span>
              </p>
            </div>
          )}
        </div>
      </div>
      <ul className="hypnogram-x" aria-hidden="true">
        <li style={{ left: "0%" }} data-edge="start">
          {clockOf(start)}
        </li>
        {ticks
          .filter((one) => one.x > 0.15 && one.x < 0.85)
          .map((one) => (
            <li key={one.label} style={{ left: `${one.x * 100}%` }}>
              {one.label}
            </li>
          ))}
        <li style={{ left: "100%" }} data-edge="end">
          {clockOf(end)}
        </li>
      </ul>
      {beats.length > 1 && (
        <ul className="series-chart-legend">
          <li>
            <span className="hypnogram-key" aria-hidden="true" />
            Vitals, de {Math.round(low)} a {Math.round(high)} lpm
          </li>
        </ul>
      )}
    </figure>
  );
}

export interface PartBar {
  label: string;
  value: string;
  share: number;
}

export function PartBars({ parts, label }: { parts: PartBar[]; label: string }) {
  return (
    <ul className="part-bars" aria-label={label}>
      {parts.map((one) => (
        <li key={one.label}>
          <span className="part-bars-name">{one.label}</span>
          <span className="part-bars-bar" aria-hidden="true">
            <span style={{ width: `${Math.max(0, Math.min(1, one.share)) * 100}%` }} />
          </span>
          <span className="part-bars-value">{one.value}</span>
        </li>
      ))}
    </ul>
  );
}

export interface StageShare {
  stage: SleepStage;
  minutes: number;
  usual?: number | null;
}

export function StageBreakdown({ stages }: { stages: StageShare[] }) {
  const total = stages.reduce((sum, one) => sum + one.minutes, 0);
  if (total <= 0) return null;
  return (
    <ul className="stage-breakdown" aria-label="Las fases de la noche">
      {stages.map((one) => {
        const share = Math.round((one.minutes / total) * 100);
        return (
          <li key={one.stage} data-stage={one.stage}>
            <span className="stage-breakdown-name">
              <span className="stage-breakdown-dot" aria-hidden="true" />
              {STAGE_NAMES[one.stage]}
            </span>
            <span className="stage-breakdown-bar" aria-hidden="true">
              <span style={{ width: `${share}%` }} />
            </span>
            <span className="stage-breakdown-value">
              {minutesText(one.minutes)} · {share} %
            </span>
            {one.usual != null && <span className="stage-breakdown-usual">normal {minutesText(one.usual)}</span>}
          </li>
        );
      })}
    </ul>
  );
}

export interface ScheduleNight {
  day: string;
  start: string;
  end: string;
  quality?: Quality | null;
}

export function nightMinute(iso: string, day: string): number {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  const midnight = new Date(year, month - 1, date).getTime();
  return Math.round((Date.parse(iso) - midnight) / MINUTE);
}

export function scheduleDomain(nights: ScheduleNight[]): { top: number; bottom: number } {
  const starts = nights.map((one) => nightMinute(one.start, one.day));
  const ends = nights.map((one) => nightMinute(one.end, one.day));
  return {
    top: Math.floor(Math.min(...starts) / 60) * 60,
    bottom: Math.ceil(Math.max(...ends) / 60) * 60,
  };
}

const hourName = (minute: number) => `${pad((((minute / 60) % 24) + 24) % 24)}:00`;

export interface SleepScheduleProps {
  nights: ScheduleNight[];
  label: string;
  formatDay?: (day: string) => string;
}

export function SleepSchedule({ nights, label, formatDay = (day) => day.slice(8) }: SleepScheduleProps) {
  if (nights.length === 0) return null;
  const { top, bottom } = scheduleDomain(nights);
  const span = Math.max(60, bottom - top);
  const y = (minute: number) => ((minute - top) / span) * 100;
  const hours = [];
  for (let minute = top; minute <= bottom; minute += span > 12 * 60 ? 180 : 120) hours.push(minute);
  return (
    <figure className="sleep-schedule" aria-label={label}>
      <div className="sleep-schedule-plot">
        <ul className="sleep-schedule-hours" aria-hidden="true">
          {hours.map((minute) => (
            <li key={minute} style={{ top: `${y(minute)}%` }}>
              {hourName(minute)}
            </li>
          ))}
        </ul>
        <ol className="sleep-schedule-bars">
          {nights.map((one) => {
            const from = y(nightMinute(one.start, one.day));
            const to = y(nightMinute(one.end, one.day));
            return (
              <li key={one.day} title={`${formatDay(one.day)}: ${clockOf(one.start)} – ${clockOf(one.end)}`}>
                <span className="sleep-schedule-bar" data-quality={one.quality ?? undefined} style={{ top: `${from}%`, height: `${Math.max(1, to - from)}%` }} />
                <span className="sleep-schedule-day" aria-hidden="true">
                  {formatDay(one.day)}
                </span>
                <span className="visually-hidden">{`${formatDay(one.day)}: de ${clockOf(one.start)} a ${clockOf(one.end)}`}</span>
              </li>
            );
          })}
        </ol>
      </div>
    </figure>
  );
}

export interface QualityDay {
  day: string;
  value: number;
  quality: Quality;
}

export interface QualityMonthProps {
  month: string;
  days: QualityDay[];
  selected?: string | null;
  onSelect?: (day: string) => void;
  onPrevious?: () => void;
  onNext?: () => void;
  label: string;
}

const MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export function monthCells(month: string): (string | null)[][] {
  const [year = 1970, number = 1] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, number - 1, 1));
  const length = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const lead = (first.getUTCDay() + 6) % 7;
  const cells: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let date = 1; date <= length; date++) cells.push(`${month}-${pad(date)}`);
  while (cells.length % 7) cells.push(null);
  const weeks = [];
  for (let index = 0; index < cells.length; index += 7) weeks.push(cells.slice(index, index + 7));
  return weeks;
}

export function QualityMonth({ month, days, selected, onSelect, onPrevious, onNext, label }: QualityMonthProps) {
  const byDay = new Map(days.map((one) => [one.day, one]));
  const [year = 1970, number = 1] = month.split("-").map(Number);
  return (
    <figure className="quality-month" aria-label={label}>
      <div className="quality-month-head">
        <button type="button" className="quality-month-step" onClick={onPrevious} disabled={!onPrevious} aria-label="Mes anterior">
          <Icon name="chevron-left" />
        </button>
        <span className="quality-month-name">{`${MONTH_NAMES[number - 1]} ${year}`}</span>
        <button type="button" className="quality-month-step" onClick={onNext} disabled={!onNext} aria-label="Mes siguiente">
          <Icon name="chevron-right" />
        </button>
      </div>
      <ol className="quality-month-weekdays" aria-hidden="true">
        {["L", "M", "X", "J", "V", "S", "D"].map((one) => (
          <li key={one}>{one}</li>
        ))}
      </ol>
      <div className="quality-month-grid" role="grid">
        {monthCells(month).map((week, row) => (
          <div key={row} className="quality-month-week" role="row">
            {week.map((day, column) => {
              if (day === null) return <span key={column} className="quality-month-cell" data-empty="" role="gridcell" />;
              const found = byDay.get(day);
              const text = `${Number(day.slice(8))}${found ? `: ${found.value}, ${QUALITY_NAMES[found.quality].toLowerCase()}` : ", sin noche"}`;
              return (
                <button
                  key={day}
                  type="button"
                  role="gridcell"
                  className="quality-month-cell"
                  data-quality={found?.quality}
                  data-selected={selected === day || undefined}
                  disabled={!found || !onSelect}
                  aria-label={text}
                  onClick={() => onSelect?.(day)}
                >
                  <span className="quality-month-date">{Number(day.slice(8))}</span>
                  {found && <span className="quality-month-score">{found.value}</span>}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <ul className="series-chart-legend">
        {(Object.keys(QUALITY_NAMES) as Quality[]).map((one) => (
          <li key={one}>
            <span className="quality-key" data-quality={one} aria-hidden="true" />
            {QUALITY_NAMES[one]}
          </li>
        ))}
      </ul>
    </figure>
  );
}

export const ZONE_SHARES = [0.5, 0.6, 0.7, 0.8, 0.9];
export const ZONE_LABELS = ["Calentamiento", "Quema de grasa", "Aeróbica", "Anaeróbica", "Máximo"];

export function zoneEdges(maxHeartRate: number): number[] {
  return ZONE_SHARES.map((share) => Math.round(share * maxHeartRate));
}

export function ZoneBar({ zones, maxHeartRate }: { zones: number[]; maxHeartRate?: number }) {
  const total = zones.reduce((sum, one) => sum + one, 0);
  const edges = maxHeartRate ? zoneEdges(maxHeartRate) : null;
  return (
    <figure className="zone-bar" aria-label="Minutos en cada zona de vitals">
      <div className="zone-bar-track" aria-hidden="true">
        {total > 0 &&
          zones.map((minutes, index) =>
            minutes > 0 ? <span key={index} data-zone={index + 1} style={{ flexGrow: minutes }} /> : null,
          )}
      </div>
      <ul className="zone-bar-legend">
        {zones.map((minutes, index) => (
          <li key={index} data-zone={index + 1}>
            <span className="zone-bar-dot" aria-hidden="true" />
            <span className="zone-bar-name">
              Zona {index + 1} · {ZONE_LABELS[index]}
            </span>
            <span className="zone-bar-range">
              {edges ? (index < 4 ? `${edges[index]}–${(edges[index + 1] ?? 0) - 1}` : `≥ ${edges[index]}`) : ""}
            </span>
            <span className="zone-bar-value">{minutesText(minutes)}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export interface HeartBeat {
  s: number;
  bpm: number;
}

export interface HeartCurveProps {
  beats: HeartBeat[];
  maxHeartRate: number;
  marks?: { s: number; label: string }[];
  seconds?: number;
  label: string;
}

export function heartDomain(beats: HeartBeat[]): { low: number; high: number } {
  const values = beats.map((one) => one.bpm);
  return {
    low: Math.floor((Math.min(...values) - 5) / 10) * 10,
    high: Math.ceil((Math.max(...values) + 5) / 10) * 10,
  };
}

const CURVE_H = 60;

export function HeartCurve({ beats, maxHeartRate, marks = [], seconds, label }: HeartCurveProps) {
  const [hover, setHover] = React.useState<number | null>(null);
  const plot = React.useRef<HTMLDivElement>(null);
  if (beats.length < 2) return <p className="widget-note">Sin vitals de esas horas.</p>;
  const { low, high } = heartDomain(beats);
  const last = Math.max(beats[beats.length - 1]?.s ?? 1, seconds ?? 0, 1);
  const x = (s: number) => (s / last) * 100;
  const y = (bpm: number) => CURVE_H - ((bpm - low) / (high - low)) * CURVE_H;
  const edges = zoneEdges(maxHeartRate);
  const bands = edges.map((edge, index) => ({
    zone: index + 1,
    from: Math.max(low, edge),
    to: Math.min(high, edges[index + 1] ?? high),
  }));
  const ticks = [high, Math.round((high + low) / 2), low];
  const shown = hover === null ? null : beats[hover];
  const nearest = (clientX: number) => {
    const box = plot.current?.getBoundingClientRect();
    if (!box || box.width === 0) return null;
    const wanted = ((clientX - box.left) / box.width) * last;
    let best = 0;
    beats.forEach((one, index) => {
      if (Math.abs(one.s - wanted) < Math.abs((beats[best]?.s ?? 0) - wanted)) best = index;
    });
    return best;
  };
  const minuteText = (s: number) => `${Math.floor(s / 60)}:${pad(Math.round(s % 60))}`;
  return (
    <figure className="series-chart heart-curve" aria-label={label}>
      <div className="series-chart-plot" ref={plot} onPointerMove={(event) => setHover(nearest(event.clientX))} onPointerLeave={() => setHover(null)}>
        <ul className="series-chart-ticks" aria-hidden="true">
          {ticks.map((value) => (
            <li key={value} style={{ top: `${(y(value) / CURVE_H) * 100}%` }}>
              {value}
            </li>
          ))}
        </ul>
        <svg viewBox={`0 0 100 ${CURVE_H}`} preserveAspectRatio="none" role="img" aria-label={label}>
          {bands
            .filter((band) => band.to > band.from)
            .map((band) => (
              <rect key={band.zone} className="heart-curve-band" data-zone={band.zone} x="0" width="100" y={y(band.to)} height={y(band.from) - y(band.to)} />
            ))}
          {seconds != null && seconds < last && <rect className="heart-curve-after" x={x(seconds)} width={100 - x(seconds)} y="0" height={CURVE_H} />}
          <polyline className="heart-curve-line" points={beats.map((one) => `${x(one.s)},${y(one.bpm)}`).join(" ")} />
          {marks.map((mark) => (
            <line key={`${mark.s}-${mark.label}`} className="heart-curve-mark" x1={x(mark.s)} x2={x(mark.s)} y1={CURVE_H - 4} y2={CURVE_H} />
          ))}
          {shown && <line className="series-chart-cursor" x1={x(shown.s)} x2={x(shown.s)} y1="0" y2={CURVE_H} />}
        </svg>
        {shown && (
          <div className="series-chart-tip" role="status" style={{ left: `${x(shown.s)}%` }} data-side={x(shown.s) > 50 ? "left" : "right"}>
            <p className="series-chart-tip-title">{minuteText(shown.s)}</p>
            <p className="series-chart-tip-row">
              <span>Vitals</span>
              <span className="series-chart-tip-value">{Math.round(shown.bpm)} lpm</span>
            </p>
            {(() => {
              const near = marks.filter((mark) => Math.abs(mark.s - shown.s) <= 60).at(-1);
              return near ? <p className="series-chart-tip-row">{near.label}</p> : null;
            })()}
          </div>
        )}
      </div>
      <ul className="trend-chart-x" aria-hidden="true">
        <li style={{ left: "0%" }} data-edge="start">
          0:00
        </li>
        <li style={{ left: "50%" }} data-edge="middle">
          {minuteText(last / 2)}
        </li>
        <li style={{ left: "100%" }} data-edge="end">
          {minuteText(last)}
        </li>
      </ul>
    </figure>
  );
}

export interface WorkoutHeartData {
  minutes: number;
  avg: number | null;
  max: number | null;
  zones: number[];
  load: number;
  recovery_2min: number | null;
  source: "band" | "day" | null;
  kcal: number | null;
  max_heart_rate: number;
  beats: HeartBeat[];
  marks: { at: string; label: string }[];
}

export const ZONES_INFO =
  "Cinco tramos de vitals sobre tu máximo teórico (220 menos tu edad): calentamiento del 50 al 60 %, quema de grasa del 60 al 70 %, aeróbica del 70 al 80 %, anaeróbica del 80 al 90 % y máximo por encima. Cuántos minutos pasaste en cada uno dice qué tipo de esfuerzo fue.";

export function heartSourceText(source: WorkoutHeartData["source"]): string {
  if (source === "band") return "Vitals de la pulsera durante el entreno.";
  if (source === "day") return "Vitals del día, minuto a minuto: la pulsera no lo registró como entreno.";
  return "Sin vitals de esas horas.";
}

export function WorkoutHeart({ heart, start }: { heart: WorkoutHeartData; start: string }) {
  const began = Date.parse(start);
  const marks = heart.marks.map((one) => ({ s: Math.max(0, Math.round((Date.parse(one.at) - began) / 1000)), label: one.label }));
  const seconds = heart.minutes * 60;
  return (
    <div className="workout-heart health-figures">
      <StatRow label="El vitals">
        <StatTile
          label="Media"
          value={heart.avg != null ? `${Math.round(heart.avg)} lpm` : "—"}
          info="Las pulsaciones por minuto de media durante el entreno, sin contar lo de después."
        />
        <StatTile
          label="Máximo"
          value={heart.max != null ? `${Math.round(heart.max)} lpm` : "—"}
          foot={heart.max != null ? `${Math.round((heart.max / heart.max_heart_rate) * 100)} % de tu máximo` : undefined}
          info="El vitals más alto del entreno, y qué parte es de tu máximo teórico (220 menos tu edad)."
        />
        <StatTile
          label="Carga"
          value={Math.round(heart.load).toLocaleString("es-ES")}
          info="Cada minuto cuenta lo que su zona, de 1 a 5 (Edwards). Las zonas, sobre 220 menos tu edad."
        />
        {heart.kcal != null && (
          <StatTile label="Calorías" value={`${Math.round(heart.kcal)} kcal`} info="Las que calcula la pulsera para ese entreno, con tu vitals y tu ficha." />
        )}
        {heart.recovery_2min != null && (
          <StatTile
            label="Recuperación"
            value={`−${Math.round(heart.recovery_2min)} lpm`}
            foot="en 2 min al acabar"
            info="Cuánto bajó el vitals en los dos minutos después de acabar. Cuanto más baja, mejor se recupera el corazón; se compara contigo mismo, no con otros."
          />
        )}
      </StatRow>
      {heart.beats.length > 1 && <HeartCurve beats={heart.beats} maxHeartRate={heart.max_heart_rate} marks={marks} seconds={seconds} label="El vitals del entreno sobre sus zonas" />}
      {heart.zones.some((one) => one > 0) && (
        <>
          <InfoHeading info={ZONES_INFO}>Zonas de vitals</InfoHeading>
          <ZoneBar zones={heart.zones} maxHeartRate={heart.max_heart_rate} />
        </>
      )}
      <Hint>
        {heartSourceText(heart.source)} Zonas sobre {heart.max_heart_rate} lpm (220 menos tu edad).
      </Hint>
    </div>
  );
}

export function hourLevel(minutes: number): 0 | 1 | 2 | 3 | 4 {
  if (minutes <= 0) return 0;
  if (minutes <= 5) return 1;
  if (minutes <= 15) return 2;
  if (minutes <= 30) return 3;
  return 4;
}

export function HourStrip({
  values,
  label,
  format,
  now,
}: {
  values: number[];
  label: string;
  format: (value: number) => string;
  now?: number;
}) {
  const hours = Array.from({ length: 24 }, (_, hour) => values[hour] ?? 0);
  return (
    <figure className="hour-strip" aria-label={label}>
      <div className="hour-strip-cells" aria-hidden="true">
        {hours.map((value, hour) => {
          const future = now !== undefined && hour > now;
          return (
            <span
              key={hour}
              className="hour-strip-cell"
              data-level={future ? undefined : hourLevel(value)}
              data-future={future || undefined}
              title={`${String(hour).padStart(2, "0")} h: ${format(value)}`}
            />
          );
        })}
      </div>
      <div className="hour-strip-axis" aria-hidden="true">
        {["00", "06", "12", "18"].map((tick) => (
          <span key={tick}>{tick}</span>
        ))}
      </div>
      <table className="visually-hidden">
        <caption>{label}</caption>
        <tbody>
          {hours.map((value, hour) => (
            <tr key={hour}>
              <th scope="row">{`${String(hour).padStart(2, "0")} h`}</th>
              <td>{now !== undefined && hour > now ? "todavía no" : format(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
