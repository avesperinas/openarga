"use client";

import * as React from "react";

import { fitsUncertaintyLine, kpiStep, type Layout, layoutOf, type WidgetSize } from "./sizes";
import { say } from "./words";

export type { WidgetSize } from "./sizes";

export type WidgetState = "loading" | "ready" | "empty" | "error" | "disconnected";

export type WidgetShape = "number" | "list";

export interface UncertaintyCandidate {
  entityId: string;
  label: string;
  weight: number;
}

export interface Uncertainty {
  summary: string;
  candidates?: UncertaintyCandidate[];
}

export type Hue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export interface WidgetProps {
  title: string;
  hue: Hue;
  appIcon?: string;
  size: WidgetSize;
  shape: WidgetShape;
  state: WidgetState;
  updatedAt?: Date;
  uncertainty?: Uncertainty;
  onRetry?: () => void;
  onConnect?: () => void;
  note?: string;
  onExamineUncertainty?: () => void;
  children?: React.ReactNode;
}

const UncertaintyContext = React.createContext<boolean>(false);

const SizeContext = React.createContext<WidgetSize | null>(null);
export const useWidgetSize = (): WidgetSize => React.useContext(SizeContext) ?? "2x2";
export const useCardSize = (): WidgetSize | null => React.useContext(SizeContext);
export const useWidgetLayout = (): Layout => layoutOf(useWidgetSize());

function ago(date: Date): string {
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes < 1) return say("widget.ago.now");
  if (minutes < 60) return say("widget.ago.minutes", { count: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return say("widget.ago.hours", { count: hours });
  return say("widget.ago.days", { count: Math.round(hours / 24) });
}

export function WidgetValue({ children }: { children: React.ReactNode }) {
  const uncertain = React.useContext(UncertaintyContext);
  return (
    <p className="widget-value" data-uncertain={uncertain || undefined}>
      {children}
    </p>
  );
}

export function WidgetDetail({ children }: { children: React.ReactNode }) {
  return <p className="widget-detail">{children}</p>;
}

function useMore(node: React.RefObject<HTMLElement | null>, element: unknown) {
  const [more, setMore] = React.useState<"above" | "below" | "both" | undefined>(undefined);
  React.useEffect(() => {
    const element = node.current;
    if (!element) return;
    const measure = () => {
      const above = element.scrollTop > 1;
      const below = element.scrollTop + element.clientHeight < element.scrollHeight - 1;
      setMore(above && below ? "both" : above ? "above" : below ? "below" : undefined);
    };
    measure();
    element.addEventListener("scroll", measure, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    if (element.firstElementChild) observer?.observe(element.firstElementChild);
    return () => {
      element.removeEventListener("scroll", measure);
      observer?.disconnect();
    };
  }, [node, element]);
  return more;
}

export function WidgetRows({
  children,
  href,
  stacked,
  columns,
}: {
  children: React.ReactNode;
  href?: string;
  stacked?: boolean;
  columns?: boolean;
}) {
  const scroller = React.useRef<HTMLElement>(null);
  const more = useMore(scroller, href);
  const list = (
    <ul
      className="widget-rows"
      data-stacked={stacked || undefined}
      data-columns={columns || undefined}
    >
      {children}
    </ul>
  );
  return href ? (
    <a
      ref={scroller as React.RefObject<HTMLAnchorElement>}
      className="widget-rows-scroll"
      href={href}
      draggable={false}
      data-more={more}
    >
      {list}
    </a>
  ) : (
    <div
      ref={scroller as React.RefObject<HTMLDivElement>}
      className="widget-rows-scroll"
      data-more={more}
    >
      {list}
    </div>
  );
}

export type RowTone = "positive" | "warning" | "negative" | "neutral";

export function WidgetRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: RowTone;
}) {
  return (
    <li className="widget-row" data-tone={tone}>
      <span className="widget-row-label">
        {tone && <span className="widget-row-dot" aria-hidden="true" />}
        <span className="widget-row-label-text">{label}</span>
      </span>
      <span className="widget-row-value">{value}</span>
    </li>
  );
}

export interface ListRowData {
  label: string;
  value: string;
  tone?: RowTone;
}

const LONG_VALUE = 7;

export function WidgetList({
  rows,
  href,
  detail,
}: {
  rows: ListRowData[];
  href?: string;
  detail?: string;
}) {
  const layout = useWidgetLayout();
  const size = useWidgetSize();
  if (layout === "tiny") {
    const urgent = rows.filter((row) => row.tone === "negative" || row.tone === "warning").length;
    return (
      <div className="list-count" data-tone={urgent ? "warning" : undefined}>
        <p className="widget-value kpi-figure">{rows.length}</p>
        {rows[0] && <p className="list-count-first">{rows[0].label}</p>}
      </div>
    );
  }
  if (layout === "strip") {
    const [first, ...rest] = rows;
    return (
      <div className="list-strip">
        {first && (
          <ul className="widget-rows" data-stacked={size === "2x1" || undefined}>
            <WidgetRow label={first.label} value={first.value} tone={first.tone} />
          </ul>
        )}
        {rest.length > 0 && <span className="list-strip-more">+{rest.length}</span>}
      </div>
    );
  }
  const columns = (layout === "wide" && rows.length > 4) || (layout === "large" && rows.length > 10);
  const half = layout === "square" || layout === "tall" || layout === "narrow" || columns;
  const stacked = half && rows.some((row) => row.value.length > LONG_VALUE);
  return (
    <>
      <WidgetRows href={href} stacked={stacked} columns={columns}>
        {rows.map((row, index) => (
          <WidgetRow key={`${row.label}-${index}`} label={row.label} value={row.value} tone={row.tone} />
        ))}
      </WidgetRows>
      {detail && <WidgetFootnote>{detail}</WidgetFootnote>}
    </>
  );
}

export function WidgetFootnote({ children }: { children: React.ReactNode }) {
  return <p className="widget-footnote">{children}</p>;
}

function Skeleton({ shape }: { shape: WidgetShape }) {
  const bars = shape === "number" ? [7, 11] : [14, 11, 13, 9];
  return (
    <div className="widget-skeleton" aria-hidden="true">
      {bars.map((width, index) => (
        <span key={index} className="widget-skeleton-bar" style={{ width: `${width * 6}%` }} />
      ))}
    </div>
  );
}

export function Widget({
  title,
  hue,
  appIcon,
  size,
  shape,
  state,
  updatedAt,
  uncertainty,
  onRetry,
  onConnect,
  note,
  onExamineUncertainty,
  children,
}: WidgetProps) {
  const showsUncertainty = state === "ready" && uncertainty !== undefined;
  const quantifies = showsUncertainty && fitsUncertaintyLine(size);

  const [plainIcon, setPlainIcon] = React.useState(false);
  return (
    <section
      className="surface widget"
      data-size={size}
      data-layout={layoutOf(size)}
      data-state={state}
      data-shape={shape}
      data-hue={hue}
      style={{ "--kpi-step": kpiStep(size) } as React.CSSProperties}
    >
      <header className="widget-header">
        {appIcon ? (
          <img
            className="widget-icon"
            src={plainIcon ? appIcon.replace(/\/icon-(solid|ink|paper)\.svg/, "/icon.svg") : appIcon}
            alt=""
            aria-hidden="true"
            draggable={false}
            onError={() => setPlainIcon(true)}
          />
        ) : (
          <span className="widget-dot" aria-hidden="true" />
        )}
        <h2 className="widget-title">{title}</h2>
      </header>

      <div className="widget-body">
        {state === "loading" && <Skeleton shape={shape} />}

        {(state === "ready" || state === "error") && (
          <SizeContext.Provider value={size}>
            <UncertaintyContext.Provider value={showsUncertainty}>
              {children}
            </UncertaintyContext.Provider>
          </SizeContext.Provider>
        )}

        {state === "empty" && (
          <p className="widget-empty">{note ?? say("widget.empty")}</p>
        )}

        {state === "error" && (
          <div className="widget-note widget-note-error">
            {updatedAt && <span className="widget-stamp">{ago(updatedAt)}</span>}
            <span>{say("widget.failed")}</span>
            {onRetry && (
              <button type="button" className="widget-action" onClick={onRetry}>
                {say("widget.retry")}
              </button>
            )}
          </div>
        )}

        {state === "disconnected" && (
          <div className="widget-note widget-note-disconnected">
            <span>{note ?? say("widget.never_synced")}</span>
            {onConnect && (
              <button type="button" className="widget-action" onClick={onConnect}>
                Conectar
              </button>
            )}
          </div>
        )}

        {quantifies && (
          <button
            type="button"
            className="widget-uncertainty"
            onClick={onExamineUncertainty}
            disabled={!onExamineUncertainty}
          >
            {uncertainty?.summary}
          </button>
        )}
      </div>
    </section>
  );
}
