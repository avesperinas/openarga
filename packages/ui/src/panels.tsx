"use client";

import * as React from "react";

import type { AgendaEntry } from "./agenda";
import { WidgetCalendar } from "./calendar";
import { SplitBar } from "./nutrition";
import { Treemap } from "./money";
import { currency, locale, numbers } from "./regional";

export type PanelHue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
export type PanelTone = "positive" | "warning" | "negative" | "neutral";
export type PanelUnit = "money" | "number" | "kg" | "percent" | "hours";

export type PanelBlock =
  | { type: "figure"; label: string; value: string; delta?: string; tone?: PanelTone; foot?: string; detail?: boolean }
  | { type: "trend"; label?: string; points: { label: string; value: number }[]; unit?: PanelUnit; detail?: boolean }
  | {
      type: "split";
      label?: string;
      total?: string;
      parts: { label: string; value: string; share: number; hue: PanelHue }[];
      detail?: boolean;
    }
  | {
      type: "tiles";
      items: { label: string; value: string; foot?: string; tone?: PanelTone; series?: number[]; href?: string }[];
      detail?: boolean;
    }
  | { type: "rings"; items: { label: string; value: string; share: number; hue: PanelHue }[]; detail?: boolean }
  | { type: "timeline"; items: { start: string; end: string; title: string; hue?: PanelHue }[]; detail?: boolean }
  | {
      type: "tasks";
      label?: string;
      widget: string;
      items: { id: string; title: string; due?: string; overdue?: boolean; done?: boolean; hue?: PanelHue }[];
      add?: string;
      detail?: boolean;
    }
  | {
      type: "list";
      label?: string;
      rows: { label: string; value: string; tone?: PanelTone; href?: string }[];
      detail?: boolean;
    }
  | { type: "alert"; text: string; tone?: PanelTone; href?: string; detail?: boolean }
  | {
      type: "bars";
      label?: string;
      labels: string[];
      values: number[];
      highlight?: number;
      goal?: number;
      unit?: PanelUnit;
      detail?: boolean;
    }
  | {
      type: "month";
      month: string;
      today?: number;
      marked?: number[];
      entries?: { start: string; end?: string; title: string; all_day?: boolean; detail?: string; tone?: number }[];
      detail?: boolean;
    }
  | { type: "treemap"; label?: string; items: { label: string; value: number; hue: PanelHue }[]; detail?: boolean }
  | {
      type: "feature";
      eyebrow?: string;
      title: string;
      text?: string;
      body?: ("chest" | "back" | "shoulders" | "arms" | "core" | "legs")[];
      action?: string;
      href?: string;
      detail?: boolean;
    };

export interface PanelTab {
  id: string;
  label: string;
  blocks: PanelBlock[];
  actions?: { label: string; href: string; primary?: boolean }[];
}

export interface PanelHeadline {
  text: string;
  emphasis?: string;
  tone?: PanelTone;
  status?: string;
}

export type PanelAct = (widget: string, verb: "complete" | "reopen" | "add", id: string) => Promise<void> | void;

const whole = () => numbers({ maximumFractionDigits: 0, useGrouping: "always" as unknown as boolean });
const oneDecimal = () => numbers({ maximumFractionDigits: 1 });

export function panelValue(value: number, unit: PanelUnit = "number"): string {
  if (unit === "money")
    return numbers({ style: "currency", currency: currency(), maximumFractionDigits: 0, minimumFractionDigits: 0, useGrouping: "always" as unknown as boolean })
      .format(value)
      .replace(/\u00a0/g, " ");
  if (unit === "kg") return `${oneDecimal().format(value)} kg`;
  if (unit === "percent") return `${whole().format(value)} %`;
  if (unit === "hours") {
    const hours = Math.floor(value);
    const minutes = Math.round((value - hours) * 60);
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  }
  return Math.abs(value) >= 100 ? whole().format(value) : oneDecimal().format(value);
}

export function Emphasised({ text, emphasis }: { text: string; emphasis?: string }) {
  if (!emphasis) return <>{text}</>;
  const at = text.indexOf(emphasis);
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <em>{emphasis}</em>
      {text.slice(at + emphasis.length)}
    </>
  );
}

export function PanelTrend({ points, unit = "number", label }: { points: { label: string; value: number }[]; unit?: PanelUnit; label?: string }) {
  const [at, setAt] = React.useState<number | null>(null);
  const plot = React.useRef<HTMLDivElement>(null);
  const values = points.map((point) => point.value);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const W = 300;
  const H = 100;
  const x = (index: number) => (index / Math.max(1, points.length - 1)) * W;
  const y = (value: number) => H - ((value - low) / span) * (H - 8) - 4;
  const line = points.map((point, index) => `${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  const shown = at ?? points.length - 1;
  const pick = (clientX: number) => {
    const box = plot.current?.getBoundingClientRect();
    if (!box || box.width === 0) return;
    const share = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
    setAt(Math.round(share * (points.length - 1)));
  };
  const point = points[shown]!;
  return (
    <figure className="panel-trend" aria-label={`${label ?? "Evolución"}: de ${panelValue(points[0]!.value, unit)} a ${panelValue(points[points.length - 1]!.value, unit)}`}>
      <div
        ref={plot}
        className="panel-trend-plot"
        role="slider"
        tabIndex={0}
        aria-label={label ?? "Evolución"}
        aria-valuemin={0}
        aria-valuemax={points.length - 1}
        aria-valuenow={shown}
        aria-valuetext={`${point.label}: ${panelValue(point.value, unit)}`}
        onPointerMove={(event) => pick(event.clientX)}
        onPointerDown={(event) => pick(event.clientX)}
        onPointerLeave={() => setAt(null)}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft") setAt(Math.max(0, shown - 1));
          if (event.key === "ArrowRight") setAt(Math.min(points.length - 1, shown + 1));
        }}
      >
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          <polygon className="panel-trend-fill" points={`0,${H} ${line} ${W},${H}`} />
          <polyline className="panel-trend-line" points={line} />
          {at !== null && <line className="panel-trend-cursor" x1={x(shown)} x2={x(shown)} y1="0" y2={H} />}
        </svg>
        <span className="panel-trend-dot" style={{ left: `${(x(shown) / W) * 100}%`, top: `${(y(point.value) / H) * 100}%` }} />
        <span
          className="panel-trend-tip"
          data-side={shown > points.length / 2 ? "left" : "right"}
          style={{ left: `${(x(shown) / W) * 100}%`, top: `${(y(point.value) / H) * 100}%` }}
        >
          {point.label} · {panelValue(point.value, unit)}
        </span>
      </div>
      <figcaption className="panel-trend-axis" aria-hidden="true">
        <span>{points[0]!.label}</span>
        <span>{points[points.length - 1]!.label}</span>
      </figcaption>
    </figure>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const line = values.map((value, index) => `${((index / (values.length - 1)) * 100).toFixed(1)},${(22 - ((value - low) / span) * 20).toFixed(1)}`).join(" ");
  return (
    <svg className="panel-spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={line} />
    </svg>
  );
}

function Ring({ share, value, hue }: { share: number; value: string; hue: PanelHue }) {
  const r = 16;
  const c = 2 * Math.PI * r;
  return (
    <svg className="panel-ring" data-hue={hue} viewBox="0 0 40 40" aria-hidden="true">
      <circle className="panel-ring-track" cx="20" cy="20" r={r} />
      <circle
        className="panel-ring-fill"
        cx="20"
        cy="20"
        r={r}
        strokeDasharray={`${(c * Math.min(1, Math.max(0, share))).toFixed(1)} ${c.toFixed(1)}`}
        transform="rotate(-90 20 20)"
      />
      <text x="20" y="23.5" textAnchor="middle">
        {value}
      </text>
    </svg>
  );
}

function hourOf(iso: string): number {
  const when = new Date(iso);
  return when.getHours() + when.getMinutes() / 60;
}

function TimelineBlock({ items, now }: { items: { start: string; end: string; title: string; hue?: PanelHue }[]; now: Date }) {
  const startHour = Math.min(8, ...items.map((one) => Math.floor(hourOf(one.start))));
  const endHour = 24;
  const at = (hour: number) => ((hour - startHour) / (endHour - startHour)) * 100;
  const current = now.getHours() + now.getMinutes() / 60;
  const ticks = [startHour, ...[12, 16, 20].filter((hour) => hour > startHour), endHour];
  return (
    <figure className="panel-timeline" aria-label={items.map((one) => `${one.title}, ${new Date(one.start).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })}`).join("; ") || "Nada hoy"}>
      <div className="panel-timeline-track" aria-hidden="true">
        <span className="panel-timeline-past" style={{ width: `${Math.min(100, Math.max(0, at(current)))}%` }} />
        {items.map((one) => (
          <span
            key={`${one.start}-${one.title}`}
            className="panel-timeline-slot"
            data-hue={one.hue ?? 1}
            data-past={hourOf(one.end) < current || undefined}
            title={one.title}
            style={{ left: `${at(hourOf(one.start))}%`, width: `${Math.max(1.2, at(hourOf(one.end)) - at(hourOf(one.start)))}%` }}
          />
        ))}
        {current >= startHour && current <= endHour && <span className="panel-timeline-now" style={{ left: `${at(current)}%` }} />}
      </div>
      <figcaption className="panel-timeline-axis" aria-hidden="true">
        {ticks.map((hour) => (
          <span key={hour} style={{ left: `${at(hour)}%` }}>
            {hour}h
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

function TasksBlock({ block, onAct }: { block: Extract<PanelBlock, { type: "tasks" }>; onAct?: PanelAct }) {
  const [busy, setBusy] = React.useState<string | null>(null);
  const [text, setText] = React.useState("");
  const run = async (key: string, action: () => Promise<void> | void) => {
    setBusy(key);
    try {
      await action();
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="panel-tasks">
      {block.label && <p className="panel-label">{block.label}</p>}
      <ul>
        {block.items.map((task) => (
          <li key={task.id} data-done={task.done || undefined}>
            <button
              type="button"
              className="panel-check"
              data-hue={task.hue ?? undefined}
              aria-pressed={Boolean(task.done)}
              aria-label={`${task.done ? "Desmarcar" : "Marcar"} ${task.title}`}
              disabled={!onAct || busy !== null}
              onClick={() => void run(task.id, () => onAct?.(block.widget, task.done ? "reopen" : "complete", task.id))}
            />
            <span className="panel-task-text">
              <span className="panel-task-title">{task.title}</span>
              {task.due && <span className="panel-task-due" data-overdue={task.overdue || undefined}>{task.due}</span>}
            </span>
          </li>
        ))}
      </ul>
      {block.add && onAct && (
        <form
          className="panel-add"
          onSubmit={(event) => {
            event.preventDefault();
            const value = text.trim();
            if (!value) return;
            void run("add", async () => {
              await onAct(block.widget, "add", value);
              setText("");
            });
          }}
        >
          <span aria-hidden="true">+</span>
          <input value={text} onChange={(event) => setText(event.target.value)} placeholder={block.add} aria-label={block.add} disabled={busy !== null} />
        </form>
      )}
    </div>
  );
}

function MonthBlock({ block }: { block: Extract<PanelBlock, { type: "month" }> }) {
  const [year, month] = block.month.split("-").map(Number);
  const entries: AgendaEntry[] | undefined = block.entries?.length
    ? block.entries.map(({ all_day, ...entry }) => ({ ...entry, allDay: all_day }))
    : undefined;
  return <WidgetCalendar month={new Date(year!, (month ?? 1) - 1, 1)} marked={block.marked ?? []} today={block.today} entries={entries} />;
}

function BarsBlock({ block }: { block: Extract<PanelBlock, { type: "bars" }> }) {
  const top = Math.max(...block.values, block.goal ?? 0) || 1;
  return (
    <figure className="panel-bars" aria-label={`${block.label ?? "Barras"}: ${block.labels.map((label, index) => `${label} ${panelValue(block.values[index] ?? 0, block.unit)}`).join(", ")}`}>
      {block.label && <figcaption className="panel-label">{block.label}</figcaption>}
      <div className="panel-bars-plot" aria-hidden="true">
        {block.goal !== undefined && <span className="panel-bars-goal" style={{ bottom: `${(block.goal / top) * 100}%` }} />}
        {block.values.map((value, index) => (
          <span key={index} className="panel-bars-col" data-on={block.highlight === undefined || block.highlight === index || undefined}>
            <span className="panel-bars-bar" style={{ height: `${Math.max(2, (value / top) * 100)}%` }} />
          </span>
        ))}
      </div>
      <div className="panel-bars-labels" aria-hidden="true">
        {block.labels.map((label, index) => (
          <span key={index}>{label}</span>
        ))}
      </div>
    </figure>
  );
}

const BODY_PARTS: Record<string, string> = {
  head: "M32 2a8 8 0 1 1 0 16a8 8 0 1 1 0-16z",
  chest: "M20 20h24v14H20z",
  core: "M21 34h22v20H21z",
  shoulders: "M12 20h8v8h-8zM44 20h8v8h-8z",
  arms: "M9 28h9v26H9zM46 28h9v26h-9z",
  legs: "M21 56h10v56H21zM33 56h10v56H33z",
};

export function BodySilhouette({ on = [] }: { on?: string[] }) {
  return (
    <svg className="panel-body" viewBox="0 0 64 114" aria-hidden="true">
      {Object.entries(BODY_PARTS).map(([part, path]) => (
        <path key={part} d={path} data-on={on.includes(part) || (part === "chest" && on.includes("back")) || undefined} />
      ))}
    </svg>
  );
}

export function PanelBlockView({ block, onAct, now = new Date() }: { block: PanelBlock; onAct?: PanelAct; now?: Date }) {
  switch (block.type) {
    case "figure":
      return (
        <div className="panel-figure">
          <p className="panel-label">{block.label}</p>
          <div className="panel-figure-row">
            <p className="panel-figure-value">{block.value}</p>
            {block.delta && (
              <span className="panel-pill" data-tone={block.tone ?? "neutral"}>
                {block.delta}
              </span>
            )}
          </div>
          {block.foot && <p className="panel-foot">{block.foot}</p>}
        </div>
      );
    case "trend":
      return <PanelTrend points={block.points} unit={block.unit} label={block.label} />;
    case "split":
      return (
        <div className="panel-split">
          {(block.label || block.total) && (
            <div className="panel-split-head">
              <span className="panel-label">{block.label}</span>
              {block.total && <span className="panel-foot">{block.total}</span>}
            </div>
          )}
          <SplitBar label={block.label ?? "Reparto"} parts={block.parts} />
        </div>
      );
    case "tiles":
      return (
        <ul className="panel-tiles">
          {block.items.map((tile) => {
            const inner = (
              <>
                <span className="panel-tile-label">{tile.label}</span>
                {tile.series && <Spark values={tile.series} />}
                <span className="panel-tile-value" data-tone={tile.tone ?? "neutral"}>
                  {tile.value}
                </span>
                {tile.foot && <span className="panel-tile-foot">{tile.foot}</span>}
              </>
            );
            return (
              <li key={tile.label} className="panel-tile">
                {tile.href ? (
                  <a className="panel-tile-body" href={tile.href}>
                    {inner}
                  </a>
                ) : (
                  <span className="panel-tile-body">{inner}</span>
                )}
              </li>
            );
          })}
        </ul>
      );
    case "rings":
      return (
        <ul className="panel-rings" data-count={Math.min(block.items.length, 5)}>
          {block.items.map((item) => (
            <li key={item.label} aria-label={`${item.label}: ${item.value}`}>
              <Ring share={item.share} value={item.value} hue={item.hue} />
              <span aria-hidden="true">{item.label}</span>
            </li>
          ))}
        </ul>
      );
    case "timeline":
      return <TimelineBlock items={block.items} now={now} />;
    case "month":
      return <MonthBlock block={block} />;
    case "tasks":
      return <TasksBlock block={block} onAct={onAct} />;
    case "list":
      return (
        <div className="panel-list">
          {block.label && <p className="panel-label">{block.label}</p>}
          <ul>
            {block.rows.map((row, index) => (
              <li key={`${row.label}-${index}`}>
                {row.href ? <a href={row.href}>{row.label}</a> : <span>{row.label}</span>}
                <b data-tone={row.tone ?? "neutral"}>{row.value}</b>
              </li>
            ))}
          </ul>
        </div>
      );
    case "alert": {
      const body = (
        <>
          <span className="panel-alert-dot" aria-hidden="true" />
          <span>{block.text}</span>
          {block.href && (
            <span className="panel-alert-go" aria-hidden="true">
              ›
            </span>
          )}
        </>
      );
      return block.href ? (
        <a className="panel-alert" data-tone={block.tone ?? "warning"} href={block.href}>
          {body}
        </a>
      ) : (
        <p className="panel-alert" data-tone={block.tone ?? "warning"}>
          {body}
        </p>
      );
    }
    case "bars":
      return <BarsBlock block={block} />;
    case "treemap":
      return (
        <div className="panel-treemap">
          {block.label && <p className="panel-label">{block.label}</p>}
          <Treemap
            label={block.label ?? "Por partes"}
            height={120}
            items={block.items.map((item) => ({ key: item.label, label: item.label, value: item.value, detail: panelValue(item.value, "money"), hue: item.hue }))}
          />
        </div>
      );
    case "feature":
      return (
        <div className="panel-feature" data-body={block.body ? "" : undefined}>
          {block.body && <BodySilhouette on={block.body} />}
          <div className="panel-feature-text">
            {block.eyebrow && <p className="panel-label">{block.eyebrow}</p>}
            <p className="panel-feature-title">{block.title}</p>
            {block.text && <p className="panel-foot">{block.text}</p>}
            {block.action && block.href && (
              <a className="panel-action" data-primary="" href={block.href}>
                {block.action}
              </a>
            )}
          </div>
        </div>
      );
  }
}

export interface AreaInfo {
  key: string;
  label: string;
  apps: string;
  hue: PanelHue;
  icon: React.ReactNode;
}

export function AreaPanel({
  area,
  headline,
  tabs,
  wide = false,
  focus = false,
  board = false,
  onExpand,
  onAct,
  now,
  tab: chosen,
  onTab,
}: {
  area: AreaInfo;
  headline?: PanelHeadline | null;
  tabs: PanelTab[];
  wide?: boolean;
  focus?: boolean;
  board?: boolean;
  onExpand?: () => void;
  onAct?: PanelAct;
  now?: Date;
  tab?: string;
  onTab?: (id: string) => void;
}) {
  const [own, setOwn] = React.useState(tabs[0]?.id ?? "");
  const active = tabs.find((one) => one.id === (chosen ?? own)) ?? tabs[0];
  const choose = (id: string) => {
    setOwn(id);
    onTab?.(id);
  };
  const blocks = (active?.blocks ?? []).filter((block) => focus || !block.detail);
  const actions = (list: PanelTab["actions"]) =>
    list && list.length > 0 ? (
      <nav className="area-panel-actions" aria-label={`Acciones de ${area.label}`}>
        {list.map((action) => (
          <a key={action.href + action.label} className="panel-action" data-primary={action.primary || undefined} href={action.href}>
            {action.label}
          </a>
        ))}
      </nav>
    ) : null;
  return (
    <section
      className="area-panel"
      data-hue={area.hue}
      data-wide={wide || undefined}
      data-focus={focus || undefined}
      data-board={board || undefined}
      aria-label={area.label}
    >
      <header className="area-panel-head">
        <span className="area-panel-icon" aria-hidden="true">
          {area.icon}
        </span>
        <span className="area-panel-name">
          <span className="area-panel-title">{area.label}</span>
          <span className="area-panel-apps">{area.apps}</span>
        </span>
        <span className="area-panel-end">
          {headline?.status && (
            <span className="panel-pill" data-tone={headline.tone ?? "neutral"}>
              {headline.status}
            </span>
          )}
          {onExpand && (
            <button type="button" className="area-panel-expand" aria-label={focus ? `Cerrar ${area.label}` : `Abrir ${area.label} en grande`} onClick={onExpand}>
              <svg viewBox="0 0 12 12" aria-hidden="true">
                {focus ? <path d="M2 2l8 8M10 2l-8 8" /> : <path d="M7 1h4v4M5 11H1V7M11 1L7 5M1 11l4-4" />}
              </svg>
            </button>
          )}
        </span>
      </header>
      {headline && (
        <p className="area-panel-headline" data-tone={headline.tone ?? "neutral"}>
          <Emphasised text={headline.text} emphasis={headline.emphasis} />
        </p>
      )}
      {board ? (
        <div className="area-panel-board" data-many={tabs.length > 4 || undefined}>
          {tabs.length === 0 && <p className="panel-foot">Aún no hay nada que contar aquí.</p>}
          {tabs.map((one) => (
            <section key={one.id} className="area-panel-column" aria-label={one.label}>
              <h3 className="area-panel-column-title">{one.label}</h3>
              <div className="area-panel-blocks">
                {one.blocks.map((block, index) => (
                  <div key={`${one.id}-${index}`} className="area-panel-block" data-type={block.type}>
                    <PanelBlockView block={block} onAct={onAct} now={now} />
                  </div>
                ))}
              </div>
              {actions(one.actions)}
            </section>
          ))}
        </div>
      ) : (
        <>
      {tabs.length > 1 && (
        <div className="area-panel-tabs" role="tablist" aria-label={`Pestañas de ${area.label}`}>
          {tabs.map((one) => (
            <button key={one.id} type="button" role="tab" aria-selected={one.id === active?.id} onClick={() => choose(one.id)}>
              {one.label}
            </button>
          ))}
        </div>
      )}
      <div className="area-panel-blocks" role={tabs.length > 1 ? "tabpanel" : undefined}>
        {blocks.length === 0 ? (
          <p className="panel-foot">Aún no hay nada que contar aquí.</p>
        ) : (
          blocks.map((block, index) => (
            <div key={`${active?.id}-${index}`} className="area-panel-block" data-type={block.type}>
              <PanelBlockView block={block} onAct={onAct} now={now} />
            </div>
          ))
        )}
      </div>
      {actions(active?.actions)}
        </>
      )}
    </section>
  );
}

export function AreaPanelSkeleton({ area, board = false }: { area: AreaInfo; board?: boolean }) {
  return (
    <section className="area-panel" data-hue={area.hue} data-board={board || undefined} aria-label={area.label} aria-busy="true">
      <header className="area-panel-head">
        <span className="area-panel-icon" aria-hidden="true">
          {area.icon}
        </span>
        <span className="area-panel-name">
          <span className="area-panel-title">{area.label}</span>
          <span className="area-panel-apps">{area.apps}</span>
        </span>
      </header>
      <div className="area-panel-resting" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    </section>
  );
}

export interface PageTab {
  key: string;
  label: string;
  icon?: React.ReactNode;
  hue?: PanelHue;
}

export function PageTabs({ items, current, onSelect }: { items: PageTab[]; current: number; onSelect: (index: number) => void }) {
  const list = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const active = list.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    active?.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [current]);
  return (
    <div className="page-tabs" role="tablist" aria-label="Páginas" ref={list}>
      {items.map((item, index) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          className="page-tab"
          data-hue={item.hue}
          aria-selected={index === current}
          onClick={() => onSelect(index)}
        >
          {item.icon && (
            <span className="page-tab-icon" aria-hidden="true">
              {item.icon}
            </span>
          )}
          {item.label}
        </button>
      ))}
    </div>
  );
}

export interface AreaOrb {
  key: string;
  label: string;
  status?: string;
  tone: PanelTone;
  hue: PanelHue;
  icon: React.ReactNode;
}

export function AreaOrbs({ items, onSelect }: { items: AreaOrb[]; onSelect?: (key: string) => void }) {
  return (
    <ul className="area-orbs" aria-label="Cómo va cada parte">
      {items.map((item) => (
        <li key={item.key}>
          <button type="button" className="area-orb" data-hue={item.hue} data-tone={item.tone} onClick={() => onSelect?.(item.key)} aria-label={`${item.label}${item.status ? `: ${item.status}` : ""}`}>
            <span className="area-orb-ball" aria-hidden="true">
              {item.icon}
            </span>
            <span className="area-orb-label" aria-hidden="true">
              {item.label}
            </span>
            {item.status && (
              <span className="area-orb-status" aria-hidden="true">
                {item.status}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
