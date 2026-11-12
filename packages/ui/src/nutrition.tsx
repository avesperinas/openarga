import * as React from "react";

import { Sparkline } from "./charts";
import { Icon } from "./icons";

export type RangeState = "low" | "ok" | "high" | "none";

export interface RangeBarProps {
  label: string;
  value: number | null;
  unit: string;
  low?: number | null;
  high?: number | null;
  state?: RangeState;
  detail?: string;
  figure?: string;
  partial?: boolean;
  onOpen?: () => void;
}

const STATE_WORDS: Record<RangeState, string> = {
  low: "Por debajo",
  ok: "En rango",
  high: "Por encima",
  none: "",
};

export function rangeScale(value: number | null, low?: number | null, high?: number | null) {
  const reach = high ?? (low ?? 0) * 1.5;
  const top = Math.max(value ?? 0, reach, 1) * 1.1;
  const at = (one: number | null | undefined) =>
    one === null || one === undefined ? null : Math.max(0, Math.min(1, one / top));
  return { value: at(value), low: at(low) ?? 0, high: at(high) ?? 1 };
}

export function RangeBar({ label, value, unit, low, high, state = "none", detail, figure, partial, onOpen }: RangeBarProps) {
  const scale = rangeScale(value, low, high);
  const shown = figure ?? (value === null ? "—" : `${Math.round(value * 10) / 10} ${unit}`);
  const words = STATE_WORDS[state];
  const body = (
    <>
      <span className="range-bar-head">
        <span className="range-bar-label">{label}</span>
        <strong className="range-bar-figure">{shown}</strong>
      </span>
      <span
        className="range-bar-track"
        role="img"
        aria-label={`${label}: ${shown}${words ? `, ${words.toLowerCase()}` : ""}`}
        style={
          {
            "--zone-from": scale.low,
            "--zone-to": scale.high,
            "--at": scale.value ?? 0,
          } as React.CSSProperties
        }
      >
        {(low !== null && low !== undefined) || (high !== null && high !== undefined) ? (
          <span className="range-bar-zone" />
        ) : null}
        {scale.value !== null && <span className="range-bar-fill" />}
        {scale.value !== null && <span className="range-bar-dot" />}
      </span>
      {(words || detail) && (
        <span className="range-bar-foot">
          {words && <span className="range-bar-state">{words}</span>}
          {detail && <span>{detail}</span>}
        </span>
      )}
    </>
  );
  return (
    <div className="range-bar" data-state={state} data-partial={partial || undefined}>
      {onOpen ? (
        <button type="button" className="range-bar-body" onClick={onOpen}>
          {body}
        </button>
      ) : (
        <div className="range-bar-body">{body}</div>
      )}
    </div>
  );
}

export type SplitHue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export interface SplitPart {
  label: string;
  value: string;
  share: number;
  hue: SplitHue;
}

export function SplitBar({
  parts,
  label,
  rest,
  palette,
}: {
  parts: SplitPart[];
  label: string;
  rest?: { label: string; value: string; share: number };
  palette?: "zones";
}) {
  const total = parts.reduce((sum, part) => sum + Math.max(0, part.share), 0) + Math.max(0, rest?.share ?? 0);
  return (
    <figure className="split-bar" data-palette={palette}>
      <span
        className="split-bar-track"
        role="img"
        aria-label={`${label}: ${[...parts, ...(rest && rest.share > 0 ? [rest] : [])].map((part) => `${part.label} ${part.value}`).join(", ")}`}
      >
        {total > 0 &&
          parts.map((part) => (
            <span
              key={part.label}
              className="split-bar-part"
              data-hue={part.hue}
              style={{ flexGrow: Math.max(0, part.share) / total }}
            />
          ))}
        {total > 0 && rest && rest.share > 0 && (
          <span className="split-bar-part" data-rest="" style={{ flexGrow: rest.share / total }} />
        )}
      </span>
      <figcaption className="split-bar-legend" aria-hidden="true">
        {parts.map((part) => (
          <span key={part.label} className="split-bar-key" data-hue={part.hue}>
            <span className="split-bar-dot" />
            <span className="split-bar-label">{part.label}</span>
            <span className="split-bar-value">{part.value}</span>
          </span>
        ))}
        {rest && rest.share > 0 && (
          <span className="split-bar-key" data-rest="">
            <span className="split-bar-dot" />
            <span className="split-bar-label">{rest.label}</span>
            <span className="split-bar-value">{rest.value}</span>
          </span>
        )}
      </figcaption>
    </figure>
  );
}

export interface CoverageItem {
  key: string;
  label: string;
  share: number | null;
  value: string;
  kind: "min" | "max";
  partial?: boolean;
  trend?: (number | null)[];
  onOpen?: () => void;
}

export type CoverageState = "low" | "near" | "ok" | "caution" | "over";

export function coverageState(item: Pick<CoverageItem, "share" | "kind">): CoverageState {
  const share = item.share ?? 0;
  if (item.kind === "max") return share > 1.1 ? "over" : share > 0.9 ? "caution" : "ok";
  if (share < 0.8) return "low";
  if (share < 1) return "near";
  return "ok";
}

export function coverageTrend(trend: (number | null)[] | undefined): "up" | "down" | null {
  if (!trend || trend.length < 3) return null;
  const last = trend.at(-1);
  const before = trend.slice(0, -1).filter((one): one is number => one !== null);
  if (last === null || last === undefined || before.length < 2) return null;
  const mean = before.reduce((sum, one) => sum + one, 0) / before.length;
  if (last - mean > 0.1) return "up";
  if (mean - last > 0.1) return "down";
  return null;
}

const COVERAGE_WORDS: Record<CoverageState, string> = {
  low: "te falta",
  near: "casi",
  ok: "bien",
  caution: "cerca del máximo",
  over: "por encima del máximo",
};

export function CoverageList({ items, label }: { items: CoverageItem[]; label: string }) {
  return (
    <ul className="coverage-list" aria-label={label}>
      {items.map((item) => {
        const state = coverageState(item);
        const pct = item.share === null ? null : Math.round(item.share * 100);
        const way = coverageTrend(item.trend);
        const said = `${item.label}: ${pct === null ? "sin dato" : `${pct} % de lo recomendado`}, ${item.value}${
          item.partial ? ", dato incompleto" : `, ${COVERAGE_WORDS[state]}`
        }${way ? `, ${way === "up" ? "sube" : "baja"} frente a las semanas de antes` : ""}`;
        const body = (
          <>
            <span className="coverage-head">
              <span className="coverage-name">{item.label}</span>
              <span className="coverage-value">
                {way && <Icon name={way === "up" ? "chevron-up" : "chevron-down"} />}
                {pct === null ? "—" : `${pct} %`} · {item.value}
              </span>
            </span>
            <span className="coverage-track" aria-hidden="true">
              <span className="coverage-fill" style={{ "--share": Math.min(1.5, item.share ?? 0) / 1.5 } as React.CSSProperties} />
              <span className="coverage-mark" />
            </span>
            {item.trend && item.trend.some((one) => one !== null) && (
              <span className="coverage-trend" aria-hidden="true">
                <Sparkline series={item.trend} />
              </span>
            )}
            {item.partial && <span className="coverage-note">dato incompleto</span>}
          </>
        );
        return (
          <li key={item.key} className="coverage-row" data-state={state} data-partial={item.partial || undefined}>
            {item.onOpen ? (
              <button type="button" className="coverage-body" aria-label={said} onClick={item.onOpen}>
                {body}
              </button>
            ) : (
              <div className="coverage-body" role="group" aria-label={said}>
                {body}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
