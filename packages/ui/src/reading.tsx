"use client";

import * as React from "react";

import { OTHERS, SERIES_COLORS } from "./analysis";
import { Icon } from "./icons";

export interface TableColumn<Row> {
  key: string;
  label: string;
  numeric?: boolean;
  cell: (row: Row) => React.ReactNode;
  csv?: (row: Row) => string | number | null;
}

export interface DataTableProps<Row> {
  label: string;
  columns: TableColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  onRowClick?: (row: Row) => void;
  rowTone?: (row: Row) => "warning" | undefined;
  footer?: React.ReactNode[];
  empty?: string;
}

export function DataTable<Row>({
  label,
  columns,
  rows,
  rowKey,
  onRowClick,
  rowTone,
  footer,
  empty = "Nada que enseñar",
}: DataTableProps<Row>) {
  if (rows.length === 0) return <p className="data-table-empty">{empty}</p>;
  return (
    <div className="data-table-scroll">
      <table className="data-table" aria-label={label}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" data-numeric={column.numeric ? "" : undefined}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              data-clickable={onRowClick ? "" : undefined}
              data-tone={rowTone?.(row)}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={
                onRowClick
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRowClick(row);
                      }
                    }
                  : undefined
              }
            >
              {columns.map((column) => (
                <td key={column.key} data-numeric={column.numeric ? "" : undefined}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && (
          <tfoot>
            <tr>
              {columns.map((column, index) => (
                <td key={column.key} data-numeric={column.numeric ? "" : undefined}>
                  {footer[index] ?? null}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

export function csvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return String(Math.round(value * 100) / 100).replace(".", ",");
  return /[";\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export function toCsv(header: string[], rows: (string | number | null | undefined)[][]): string {
  return [header, ...rows].map((row) => row.map(csvCell).join(";")).join("\n");
}

export function tableCsv<Row>(columns: TableColumn<Row>[], rows: Row[]): string {
  return toCsv(
    columns.map((column) => column.label),
    rows.map((row) =>
      columns.map((column) => {
        if (column.csv) return column.csv(row);
        const shown = column.cell(row);
        return typeof shown === "string" || typeof shown === "number" ? shown : "";
      }),
    ),
  );
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export interface ShareItem {
  key: string;
  name: string;
  value: number;
}

export function foldShares(items: ShareItem[], order: string[] = [], max = SERIES_COLORS): ShareItem[] {
  const positive = items.filter((one) => one.value > 0).sort((a, b) => b.value - a.value);
  const kept = positive.slice(0, max);
  const rest = positive.slice(max);
  const position = (key: string) => {
    const at = order.indexOf(key);
    return at === -1 ? order.length + positive.findIndex((one) => one.key === key) : at;
  };
  kept.sort((a, b) => position(a.key) - position(b.key));
  if (rest.length === 0) return kept;
  return [...kept, { key: OTHERS, name: "Otros", value: rest.reduce((sum, one) => sum + one.value, 0) }];
}

export function percentOf(value: number, total: number): string {
  if (total <= 0) return "—";
  const percent = (value / total) * 100;
  return percent > 0 && percent < 1 ? "<1 %" : `${Math.round(percent)} %`;
}

function arc(start: number, end: number, outer: number, inner: number): string {
  const point = (angle: number, radius: number) => `${50 + radius * Math.sin(angle)} ${50 - radius * Math.cos(angle)}`;
  const large = end - start > Math.PI ? 1 : 0;
  return [
    `M ${point(start, outer)}`,
    `A ${outer} ${outer} 0 ${large} 1 ${point(end, outer)}`,
    `L ${point(end, inner)}`,
    `A ${inner} ${inner} 0 ${large} 0 ${point(start, inner)}`,
    "Z",
  ].join(" ");
}

export interface ShareChartProps {
  label: string;
  items: ShareItem[];
  order?: string[];
  format?: (value: number) => string;
  center?: string;
}

export function ShareChart({
  label,
  items,
  order = [],
  format = (value) => value.toLocaleString("es-ES"),
  center,
}: ShareChartProps) {
  const shown = foldShares(items, order);
  const total = shown.reduce((sum, one) => sum + one.value, 0);
  if (shown.length === 0 || total <= 0) return <p className="widget-note">Sin datos que repartir</p>;
  let angle = 0;
  const colour = (key: string, index: number) => (key === OTHERS ? "others" : String(index));
  return (
    <figure className="share-chart" aria-label={label}>
      <svg viewBox="0 0 100 100" role="img" aria-label={label}>
        {shown.length === 1 ? (
          <circle className="share-chart-slice" data-series="0" cx="50" cy="50" r="40" />
        ) : (
          shown.map((one, index) => {
            const start = angle;
            angle += (one.value / total) * Math.PI * 2;
            return (
              <path
                key={one.key}
                className="share-chart-slice"
                data-series={colour(one.key, index)}
                d={arc(start, angle, 48, 30)}
              />
            );
          })
        )}
        {shown.length === 1 && <circle className="share-chart-hole" cx="50" cy="50" r="30" />}
        <text className="share-chart-center" x="50" y="50" textAnchor="middle" dominantBaseline="central">
          {center ?? format(total)}
        </text>
      </svg>
      <ul className="share-chart-legend">
        {shown.map((one, index) => (
          <li key={one.key}>
            <span className="series-chart-swatch" data-series={colour(one.key, index)} aria-hidden="true" />
            <span className="share-chart-name">{one.name}</span>
            <span className="share-chart-percent">{percentOf(one.value, total)}</span>
            <span className="share-chart-value">{format(one.value)}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export type StatTone = "positive" | "warning" | "negative" | "neutral";

export function toneFor(percent: number | null | undefined): StatTone {
  if (percent === null || percent === undefined || Number.isNaN(percent)) return "neutral";
  if (percent >= 100) return "positive";
  if (percent >= 50) return "warning";
  return "negative";
}

export interface StatTileProps {
  label: string;
  value: string;
  foot?: string;
  tone?: StatTone;
  progress?: number | null;
  onClick?: () => void;
  info?: React.ReactNode;
}

export function StatTile({ label, value, foot, tone = "neutral", progress, onClick, info }: StatTileProps) {
  const [explaining, setExplaining] = React.useState(false);
  const body = (
    <>
      <span className="stat-tile-label">{label}</span>
      <span className="stat-tile-value">{value}</span>
      {progress !== undefined && progress !== null && (
        <span className="stat-tile-bar" aria-hidden="true">
          <span style={{ width: `${Math.max(0, Math.min(1, progress)) * 100}%` }} />
        </span>
      )}
      {foot && <span className="stat-tile-foot">{foot}</span>}
    </>
  );
  const why = info ? (
    <>
      <button
        type="button"
        className="stat-tile-info"
        aria-label={
          explaining ? `Cerrar cómo se calcula ${label.toLowerCase()}` : `Cómo se calcula ${label.toLowerCase()}`
        }
        aria-expanded={explaining}
        onClick={() => setExplaining(!explaining)}
      >
        <Icon name={explaining ? "close" : "info"} />
      </button>
      {explaining && <div className="stat-tile-why">{info}</div>}
    </>
  ) : null;
  return (
    <div className="stat-tile" data-tone={tone}>
      {onClick ? (
        <button type="button" className="stat-tile-body" onClick={onClick}>
          {body}
        </button>
      ) : (
        <div className="stat-tile-body">{body}</div>
      )}
      {why}
    </div>
  );
}

export function StatRow({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <section className="stat-row" aria-label={label}>
      {children}
    </section>
  );
}

export interface CollapsibleProps {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export function Collapsible({ title, subtitle, defaultOpen = false, children }: CollapsibleProps) {
  return (
    <details className="collapsible" open={defaultOpen || undefined}>
      <summary>
        <span className="collapsible-text">
          <span className="collapsible-title">{title}</span>
          {subtitle && <span className="collapsible-subtitle">{subtitle}</span>}
        </span>
        <Icon name="chevron-down" />
      </summary>
      <div className="collapsible-body">{children}</div>
    </details>
  );
}

export interface MultiSelectFieldProps<T extends string> {
  label: string;
  options: { value: T; label: string }[];
  values: T[];
  onChange: (values: T[]) => void;
  all?: string;
  hideLabel?: boolean;
}

export function MultiSelectField<T extends string>({ label, options, values, onChange, all = "Todas", hideLabel }: MultiSelectFieldProps<T>) {
  const id = React.useId();
  const [open, setOpen] = React.useState(false);
  const box = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  const picked = options.filter((o) => values.includes(o.value));
  const text = !picked.length ? all : picked.length <= 2 ? picked.map((o) => o.label).join(", ") : `${picked.length} elegidas`;
  const toggle = (value: T) =>
    onChange(values.includes(value) ? values.filter((v) => v !== value) : options.filter((o) => o.value === value || values.includes(o.value)).map((o) => o.value));
  return (
    <div className="select-field multi-select" ref={box}>
      <span id={`${id}-label`} className={hideLabel ? "visually-hidden" : "text-field-label"}>
        {label}
      </span>
      <div className="select-field-box">
        <button
          type="button"
          className="multi-select-button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-labelledby={`${id}-label ${id}-value`}
          data-picked={picked.length > 0 || undefined}
          onClick={() => setOpen((o) => !o)}
        >
          <span id={`${id}-value`}>{text}</span>
        </button>
        <Icon name="chevron-down" />
      </div>
      {open && (
        <ul className="multi-select-list" role="listbox" aria-multiselectable="true" aria-labelledby={`${id}-label`}>
          {options.map((o) => {
            const on = values.includes(o.value);
            return (
              <li key={o.value} role="none">
                <button type="button" role="option" aria-selected={on} className="multi-select-option" onClick={() => toggle(o.value)}>
                  <span className="multi-select-check" data-on={on || undefined}>
                    {on && <Icon name="done" />}
                  </span>
                  {o.label}
                </button>
              </li>
            );
          })}
          {values.length > 0 && (
            <li role="none">
              <button type="button" className="multi-select-option multi-select-clear" onClick={() => onChange([])}>
                Quitar la selección
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export interface SelectFieldProps<T extends string> {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  hideLabel?: boolean;
}

export function SelectField<T extends string>({ label, options, value, onChange, hideLabel }: SelectFieldProps<T>) {
  const id = React.useId();
  return (
    <div className="select-field">
      <label htmlFor={id} className={hideLabel ? "visually-hidden" : "text-field-label"}>
        {label}
      </label>
      <div className="select-field-box">
        <select id={id} value={value} onChange={(event) => onChange(event.target.value as T)}>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon name="chevron-down" />
      </div>
    </div>
  );
}
