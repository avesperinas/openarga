import * as React from "react";

export interface RingFigureProps {
  share: number | null;
  value: React.ReactNode;
  label: string;
  detail?: React.ReactNode;
  size?: "large" | "medium";
  tone?: "positive" | "info" | "warning" | "negative";
  planned?: number | null;
}

export function RingFigure({ share, value, label, detail, size = "large", tone, planned }: RingFigureProps) {
  const known = share !== null && Number.isFinite(share);
  const filled = known ? Math.max(0, Math.min(1, share)) * 100 : 0;
  const ahead = planned !== null && planned !== undefined && Number.isFinite(planned) ? Math.max(0, Math.min(1, planned)) * 100 : 0;
  return (
    <figure className="share-ring" data-size={size} data-tone={tone}>
      <span className="share-ring-ring">
        <svg viewBox="0 0 40 40" aria-hidden="true">
          <circle className="share-ring-track" cx="20" cy="20" r="16" />
          {ahead > filled && (
            <circle
              className="share-ring-planned"
              cx="20"
              cy="20"
              r="16"
              pathLength={100}
              strokeDasharray={`${ahead} 100`}
              transform="rotate(-90 20 20)"
            />
          )}
          {known && filled > 0 && (
            <circle
              className="share-ring-fill"
              cx="20"
              cy="20"
              r="16"
              pathLength={100}
              strokeDasharray={`${filled} 100`}
              transform="rotate(-90 20 20)"
            />
          )}
        </svg>
        <span className="share-ring-value">{value}</span>
      </span>
      <figcaption className="share-ring-text">
        <span className="share-ring-label">{label}</span>
        {detail && <span className="share-ring-detail">{detail}</span>}
      </figcaption>
    </figure>
  );
}

export interface FrequencyBarProps {
  since: number | null;
  every: number | null;
  label: string;
}

export function FrequencyBar({ since, every, label }: FrequencyBarProps) {
  const top = Math.max(since ?? 0, every ?? 0, 1);
  const over = since !== null && every !== null && since >= every;
  const fill = since === null ? 0 : (since / top) * 100;
  return (
    <span className="frequency-bar" role="img" aria-label={label} data-over={over || undefined}>
      <span className="frequency-bar-fill" style={{ width: `${fill}%` }} />
      {every !== null && <span className="frequency-bar-mark" style={{ left: `${(every / top) * 100}%` }} />}
    </span>
  );
}

export interface DaySpan {
  from: number;
  to: number;
}

export interface DayTimelineProps {
  label: string;
  marks?: number[];
  spans?: DaySpan[];
  now?: number;
  name?: string;
  state?: "today" | "off";
  quiet?: boolean;
  onClick?: () => void;
  size?: "regular" | "large";
}

const at = (hour: number) => `${(Math.max(0, Math.min(24, hour)) / 24) * 100}%`;

export function DayTimeline({ label, marks = [], spans = [], now, name, state, quiet = false, onClick, size = "regular" }: DayTimelineProps) {
  const bar = (
    <span className="day-timeline-bar" role="img" aria-label={label}>
      {spans.map((span, index) => (
        <span
          key={`s${index}`}
          className="day-timeline-span"
          style={{ left: at(span.from), width: `calc(${at(span.to)} - ${at(span.from)})` }}
        />
      ))}
      {marks.map((hour, index) => (
        <span key={`m${index}`} className="day-timeline-mark" style={{ left: at(hour) }} />
      ))}
      {now !== undefined && <span className="day-timeline-now" style={{ left: at(now) }} />}
    </span>
  );
  const content = (
    <>
      {name && (
        <span className="day-timeline-name" aria-hidden="true">
          {name}
        </span>
      )}
      {bar}
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        className="day-timeline"
        data-state={state}
        data-size={size}
        data-named={name ? "" : undefined}
        data-quiet={quiet || undefined}
        onClick={onClick}
      >
        {content}
      </button>
    );
  }
  return (
    <div className="day-timeline" data-state={state} data-size={size} data-named={name ? "" : undefined} data-quiet={quiet || undefined}>
      {content}
    </div>
  );
}

export function DayTimelineAxis({ named = false }: { named?: boolean }) {
  return (
    <div className="day-timeline-axis" data-named={named ? "" : undefined} aria-hidden="true">
      <span />
      <span className="day-timeline-hours">
        {[0, 6, 12, 18, 24].map((hour) => (
          <span key={hour}>{hour}</span>
        ))}
      </span>
    </div>
  );
}

export function DayTimelines({ children, axis = true, named = true }: { children: React.ReactNode; axis?: boolean; named?: boolean }) {
  return (
    <div className="day-timelines">
      {children}
      {axis && <DayTimelineAxis named={named} />}
    </div>
  );
}

export interface FrequencyRowProps extends FrequencyBarProps {
  title: string;
  value?: string;
  onClick?: () => void;
}

export function FrequencyRow({ title, value, onClick, ...bar }: FrequencyRowProps) {
  const over = bar.since !== null && bar.every !== null && bar.since >= bar.every;
  const content = (
    <>
      <span className="frequency-row-title">{title}</span>
      <FrequencyBar {...bar} />
      {value && (
        <span className="frequency-row-value" data-over={over || undefined}>
          {value}
        </span>
      )}
    </>
  );
  return (
    <li>
      {onClick ? (
        <button type="button" className="frequency-row" onClick={onClick}>
          {content}
        </button>
      ) : (
        <div className="frequency-row">{content}</div>
      )}
    </li>
  );
}

export function FrequencyRows({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <ul className="surface frequency-rows" aria-label={label}>
      {children}
    </ul>
  );
}
