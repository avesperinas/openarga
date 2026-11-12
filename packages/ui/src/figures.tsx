import * as React from "react";

export type DeltaDirection = "up" | "flat" | "down" | "first";

export function Delta({ text, direction, label }: { text: string; direction: DeltaDirection; label?: string }) {
  return (
    <span className="delta" data-direction={direction} aria-label={label}>
      {label ? <span aria-hidden="true">{text}</span> : text}
    </span>
  );
}

export interface Figure {
  label: string;
  value: React.ReactNode;
  lit?: boolean;
  muted?: boolean;
}

export function Figures({ items, label }: { items: Figure[]; label?: string }) {
  return (
    <div className="figures-frame">
      <dl className="figures" aria-label={label} data-count={items.length}>
        {items.map((item) => (
          <div key={item.label} data-lit={item.lit ? "" : undefined} data-muted={item.muted ? "" : undefined}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export interface HeadlineFigureProps {
  label: string;
  value: React.ReactNode;
  unit?: string;
  change?: { text: string; direction: DeltaDirection };
  tone?: "positive" | "warning" | "negative";
}

export function HeadlineFigure({ label, value, unit, change, tone }: HeadlineFigureProps) {
  return (
    <div className="headline-figure" data-tone={tone}>
      <p className="headline-figure-main">
        <span className="headline-figure-label">{label}</span>
        <span className="headline-figure-value">
          {value}
          {unit && <span className="headline-figure-unit"> {unit}</span>}
        </span>
      </p>
      {change && <Delta text={change.text} direction={change.direction} />}
    </div>
  );
}

export function ProgressRing({ done, target }: { done: number; target: number }) {
  const share = target > 0 ? Math.min(done / target, 1) : 0;
  const complete = target > 0 && done >= target;
  return (
    <span className="progress-ring" data-complete={complete || undefined} aria-hidden="true">
      <svg viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15" className="progress-ring-track" />
        <circle
          cx="18"
          cy="18"
          r="15"
          className="progress-ring-fill"
          pathLength={100}
          strokeDasharray={`${share * 100} 100`}
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span className="progress-ring-label">{complete ? "✓" : done}</span>
    </span>
  );
}
