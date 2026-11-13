"use client";

import * as React from "react";

import { InfoButton } from "./health";
import { locale } from "./regional";

export type Hue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
export type MoneyTone = "positive" | "negative" | "neutral";

export interface AreaTrendProps {
  label: string;
  value: React.ReactNode;
  delta?: { text: string; tone: MoneyTone };
  points: { label: string; value: number | null }[];
  aside?: React.ReactNode;
  children?: React.ReactNode;
  description?: string;
  info?: React.ReactNode;
}

const AW = 300;
const AH = 80;

export function areaPath(values: (number | null)[]): { line: string; fill: string; last: { x: number; y: number } | null } {
  const known = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (known.length === 0) return { line: "", fill: "", last: null };
  const min = Math.min(...known);
  const max = Math.max(...known);
  const room = max - min || Math.abs(max) || 1;
  const low = min - room * 0.12;
  const high = max + room * 0.12;
  const x = (index: number) => (values.length === 1 ? AW : (index / (values.length - 1)) * AW);
  const y = (value: number) => AH - ((value - low) / (high - low)) * AH;
  let line = "";
  let fill = "";
  let open: { x: number; y: number }[] = [];
  const close = () => {
    if (open.length === 0) return;
    const path = open.map((p, index) => `${index === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    line += `${path} `;
    fill += `${path} L${open[open.length - 1]!.x.toFixed(1)},${AH} L${open[0]!.x.toFixed(1)},${AH} Z `;
    open = [];
  };
  let last: { x: number; y: number } | null = null;
  values.forEach((value, index) => {
    if (value === null || !Number.isFinite(value)) return close();
    last = { x: x(index), y: y(value) };
    open.push(last);
  });
  close();
  return { line: line.trim(), fill: fill.trim(), last };
}

export function AreaTrend({ label, value, delta, points, aside, children, description, info }: AreaTrendProps) {
  const [explaining, setExplaining] = React.useState(false);
  const { line, fill, last } = areaPath(points.map((point) => point.value));
  const first = points[0]?.label;
  const end = points[points.length - 1]?.label;
  return (
    <section className="area-trend" aria-label={label}>
      <header className="area-trend-head">
        <span className="area-trend-label">
          {label}
          {info && <InfoButton label={label} open={explaining} onToggle={() => setExplaining(!explaining)} />}
        </span>
        {aside}
      </header>
      {explaining && info && <div className="info-why">{info}</div>}
      <p className="area-trend-value">{value}</p>
      {delta && (
        <p className="area-trend-delta" data-tone={delta.tone}>
          {delta.text}
        </p>
      )}
      {line && (
        <figure className="area-trend-plot">
          <svg viewBox={`0 0 ${AW} ${AH}`} preserveAspectRatio="none" role="img" aria-label={description ?? `${label}: de ${first} a ${end}`}>
            <path className="area-trend-fill" d={fill} />
            <path className="area-trend-line" d={line} />
          </svg>
          {last && (
            <span
              className="area-trend-dot"
              aria-hidden="true"
              style={{ left: `${(last.x / AW) * 100}%`, top: `${(last.y / AH) * 100}%` }}
            />
          )}
          <figcaption className="area-trend-axis" aria-hidden="true">
            <span>{first}</span>
            <span>{end}</span>
          </figcaption>
        </figure>
      )}
      {children}
    </section>
  );
}

export interface StripItem {
  key: string;
  label: string;
  value: number | null;
  description: string;
}

export function MonthStrip({
  items,
  selected,
  onSelect,
  label,
}: {
  items: StripItem[];
  selected: string | null;
  onSelect: (key: string) => void;
  label: string;
}) {
  const scroller = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const element = scroller.current;
    const chosen = element?.querySelector<HTMLElement>("[aria-pressed='true']");
    if (element && chosen) element.scrollLeft = chosen.offsetLeft - element.clientWidth + chosen.offsetWidth * 2;
  }, [selected, items.length]);
  const top = Math.max(0, ...items.map((item) => item.value ?? 0));
  return (
    <div className="month-strip" ref={scroller} role="group" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className="month-strip-item"
          aria-pressed={item.key === selected}
          aria-label={item.description}
          onClick={() => onSelect(item.key)}
        >
          <span className="month-strip-track" aria-hidden="true">
            {item.value !== null && top > 0 && (
              <span className="month-strip-bar" style={{ height: `${Math.max(4, (item.value / top) * 100)}%` }} />
            )}
          </span>
          <span className="month-strip-label" aria-hidden="true">
            {item.label}
          </span>
        </button>
      ))}
    </div>
  );
}

export interface Party {
  name: string;
  hue: Hue;
}

export function BalanceHero({
  payer,
  payee,
  amount,
  detail,
  even = false,
  action,
}: {
  payer: Party;
  payee: Party;
  amount: React.ReactNode;
  detail?: React.ReactNode;
  even?: boolean;
  action?: React.ReactNode;
}) {
  const initial = (party: Party) => party.name.trim().charAt(0).toUpperCase() || "?";
  return (
    <section className="balance-hero" aria-label={even ? "Estáis en paz" : `${payer.name} paga a ${payee.name}`}>
      <div className="balance-hero-parties" aria-hidden="true">
        <span className="balance-hero-person" data-hue={payer.hue}>
          <span className="balance-hero-avatar">{initial(payer)}</span>
          <span className="balance-hero-name">{payer.name}</span>
        </span>
        <span className="balance-hero-arrow" data-even={even || undefined}>
          <svg viewBox="0 0 80 16" preserveAspectRatio="none">
            <line x1="2" x2={even ? 78 : 68} y1="8" y2="8" />
            {!even && <path d="M66,2 L78,8 L66,14 Z" />}
          </svg>
        </span>
        <span className="balance-hero-person" data-hue={payee.hue}>
          <span className="balance-hero-avatar">{initial(payee)}</span>
          <span className="balance-hero-name">{payee.name}</span>
        </span>
      </div>
      <p className="balance-hero-amount">{amount}</p>
      {detail && <p className="balance-hero-detail">{detail}</p>}
      {action}
    </section>
  );
}

const GW = 300;
const GH = 120;

export function GainChart({
  labels,
  value,
  contributed,
  label,
  format = (amount) => amount.toLocaleString(locale()),
}: {
  labels: string[];
  value: (number | null)[];
  contributed: number[];
  label: string;
  format?: (amount: number) => string;
}) {
  const known = [...value.filter((one): one is number => one !== null), ...contributed];
  if (labels.length === 0 || known.length === 0) return <p className="widget-note">Sin datos en este rango</p>;
  const high = Math.max(...known);
  const low = Math.min(...known);
  const room = high - low || Math.abs(high) || 1;
  const top = high + room * 0.15;
  const bottom = low - room * 0.15;
  const x = (index: number) => (labels.length === 1 ? GW / 2 : (index / (labels.length - 1)) * GW);
  const y = (amount: number) => GH - ((amount - bottom) / (top - bottom || 1)) * GH;
  const pairs = labels.map((_, index) => ({ index, v: value[index] ?? null, c: contributed[index] ?? 0 }));
  const shown = pairs.filter((pair) => pair.v !== null) as { index: number; v: number; c: number }[];
  const valueLine = shown.map((pair, at) => `${at ? "L" : "M"}${x(pair.index).toFixed(1)},${y(pair.v).toFixed(1)}`).join(" ");
  const putLine = pairs.map((pair, at) => `${at ? "L" : "M"}${x(pair.index).toFixed(1)},${y(pair.c).toFixed(1)}`).join(" ");
  const between = shown.length
    ? `${shown.map((pair, at) => `${at ? "L" : "M"}${x(pair.index).toFixed(1)},${y(pair.v).toFixed(1)}`).join(" ")} ${[...shown]
        .reverse()
        .map((pair) => `L${x(pair.index).toFixed(1)},${y(pair.c).toFixed(1)}`)
        .join(" ")} Z`
    : "";
  const lastShown = shown[shown.length - 1];
  const ahead = lastShown ? lastShown.v >= lastShown.c : true;
  return (
    <figure className="gain-chart" aria-label={label}>
      <svg viewBox={`0 0 ${GW} ${GH}`} preserveAspectRatio="none" role="img" aria-label={label}>
        <line className="gain-chart-grid" x1="0" x2={GW} y1={GH / 2} y2={GH / 2} />
        {between && <path className="gain-chart-gain" data-ahead={ahead || undefined} d={between} />}
        <path className="gain-chart-put" d={putLine} />
        <path className="gain-chart-value" d={valueLine} />
      </svg>
      <figcaption className="gain-chart-legend">
        <span className="gain-chart-key" data-key="value">
          Lo que vale
        </span>
        <span className="gain-chart-key" data-key="put">
          Lo aportado
        </span>
        <span className="gain-chart-key" data-key="gain" data-ahead={ahead || undefined}>
          {ahead ? "Ganancia" : "Pérdida"}
        </span>
        <span className="gain-chart-range">
          {labels[0]} – {labels[labels.length - 1]}
        </span>
      </figcaption>
      <details className="series-chart-table">
        <summary>Ver como tabla</summary>
        <div className="series-chart-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Mes</th>
                <th scope="col">Vale</th>
                <th scope="col">Aportado</th>
              </tr>
            </thead>
            <tbody>
              {pairs.map((pair) => (
                <tr key={labels[pair.index]! + pair.index}>
                  <th scope="row">{labels[pair.index]}</th>
                  <td>{pair.v === null ? "—" : format(pair.v)}</td>
                  <td>{format(pair.c)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

export interface TreemapItem {
  key: string;
  label: string;
  value: number;
  detail: string;
  hue: Hue;
  mark?: string;
}

export interface TreemapTile extends TreemapItem {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function treemapLayout(items: TreemapItem[], width: number, height: number): TreemapTile[] {
  const positive = items.filter((item) => item.value > 0).sort((a, b) => b.value - a.value);
  const total = positive.reduce((sum, item) => sum + item.value, 0);
  if (total <= 0) return [];
  const scale = (width * height) / total;
  const out: TreemapTile[] = [];
  const rest = positive.map((item) => ({ item, area: item.value * scale }));
  let box = { x: 0, y: 0, w: width, h: height };
  const worst = (row: number[], side: number) => {
    const sum = row.reduce((a, b) => a + b, 0);
    const max = Math.max(...row);
    const min = Math.min(...row);
    return Math.max((side * side * max) / (sum * sum), (sum * sum) / (side * side * min));
  };
  while (rest.length > 0) {
    const side = Math.min(box.w, box.h);
    const row: typeof rest = [];
    while (rest.length > 0) {
      const next = [...row, rest[0]!].map((one) => one.area);
      if (row.length > 0 && worst(next, side) > worst(row.map((one) => one.area), side)) break;
      row.push(rest.shift()!);
    }
    const sum = row.reduce((a, one) => a + one.area, 0);
    if (box.w >= box.h) {
      const w = sum / box.h;
      let y = box.y;
      for (const one of row) {
        const h = one.area / w;
        out.push({ ...one.item, x: box.x, y, w, h });
        y += h;
      }
      box = { x: box.x + w, y: box.y, w: box.w - w, h: box.h };
    } else {
      const h = sum / box.w;
      let x = box.x;
      for (const one of row) {
        const w = one.area / h;
        out.push({ ...one.item, x, y: box.y, w, h });
        x += w;
      }
      box = { x: box.x, y: box.y + h, w: box.w, h: box.h - h };
    }
  }
  return out;
}

export function Treemap({
  items,
  label,
  onSelect,
  height = 220,
}: {
  items: TreemapItem[];
  label: string;
  onSelect?: (key: string) => void;
  height?: number;
}) {
  const tiles = treemapLayout(items, 100, 100);
  if (tiles.length === 0) return <p className="widget-note">Sin datos en este rango</p>;
  return (
    <div className="treemap" role="group" aria-label={label} style={{ height }}>
      {tiles.map((tile) => {
        const tall = (tile.h / 100) * height;
        const named = tall >= 26 && tile.w >= 14;
        const body = (
          <>
            {named && (
              <span className="treemap-name">
                {tile.label}
                {tile.mark ? ` ${tile.mark}` : ""}
              </span>
            )}
            {named && tall >= 46 && <span className="treemap-detail">{tile.detail}</span>}
          </>
        );
        const style = { left: `${tile.x}%`, top: `${tile.y}%`, width: `${tile.w}%`, height: `${tile.h}%` };
        const name = `${tile.label}: ${tile.detail}`;
        return onSelect ? (
          <button key={tile.key} type="button" className="treemap-tile" data-hue={tile.hue} style={style} aria-label={name} title={name} onClick={() => onSelect(tile.key)}>
            {body}
          </button>
        ) : (
          <span key={tile.key} className="treemap-tile" data-hue={tile.hue} style={style} role="img" aria-label={name} title={name}>
            {body}
          </span>
        );
      })}
    </div>
  );
}

export interface DivergingRow {
  key: string;
  label: string;
  value: number;
  text: string;
  tone: MoneyTone;
}

export function DivergingBars({ rows, label, onSelect }: { rows: DivergingRow[]; label: string; onSelect?: (key: string) => void }) {
  const top = Math.max(0, ...rows.map((row) => Math.abs(row.value)));
  if (rows.length === 0) return null;
  return (
    <ul className="diverging" aria-label={label}>
      {rows.map((row) => {
        const share = top > 0 ? (Math.abs(row.value) / top) * 50 : 0;
        const bar = (
          <>
            <span className="diverging-label">{row.label}</span>
            <span className="diverging-track" aria-hidden="true">
              <span
                className="diverging-bar"
                data-tone={row.tone}
                style={row.value >= 0 ? { left: "50%", width: `${share}%` } : { right: "50%", width: `${share}%` }}
              />
            </span>
            <span className="diverging-text" data-tone={row.tone}>
              {row.text}
            </span>
          </>
        );
        return (
          <li key={row.key}>
            {onSelect ? (
              <button type="button" className="diverging-row" onClick={() => onSelect(row.key)} aria-label={`${row.label}: ${row.text}`}>
                {bar}
              </button>
            ) : (
              <span className="diverging-row" aria-label={`${row.label}: ${row.text}`}>
                {bar}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
