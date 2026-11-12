import * as React from "react";

import { Sparkline } from "./charts";
import { InfoButton, RingArc } from "./health";
import { Icon, type IconName } from "./icons";

export type VitalTone = "good" | "fair" | "poor" | "neutral";

export interface VitalCardProps {
  label: string;
  icon: IconName;
  ring: {
    value: number;
    target: number;
    display: string;
    mark?: number;
  };
  verdict: string;
  tone: VitalTone;
  detail?: string;
  info?: React.ReactNode;
  onOpen?: () => void;
}

export function VitalCard({ label, icon, ring, verdict, tone, detail, info, onOpen }: VitalCardProps) {
  const [open, setOpen] = React.useState(false);
  const filled = ring.target > 0 ? ring.value / ring.target : 0;
  const body = (
    <>
      <span className="vital-card-head">
        <Icon name={icon} />
        <span>{label}</span>
      </span>
      <span className="vital-card-ring">
        <RingArc filled={filled} mark={ring.mark} />
        <span className="vital-card-figure">{ring.display}</span>
      </span>
      <span className="vital-card-verdict">{verdict}</span>
      {detail && <span className="vital-card-detail">{detail}</span>}
      {onOpen && (
        <span className="vital-card-go" aria-hidden="true">
          <Icon name="chevron-right" />
        </span>
      )}
    </>
  );
  return (
    <div className="surface vital-card" data-tone={tone}>
      {onOpen ? (
        <button type="button" className="vital-card-body" onClick={onOpen} aria-label={`${label}: ${verdict}`}>
          {body}
        </button>
      ) : (
        <div className="vital-card-body">{body}</div>
      )}
      {info && (
        <span className="vital-card-info">
          <InfoButton label={label} open={open} onToggle={() => setOpen(!open)} />
        </span>
      )}
      {open && info && <div className="info-why vital-card-why">{info}</div>}
    </div>
  );
}

export function VitalCards({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="vital-cards" aria-label={label}>
      {children}
    </section>
  );
}

export interface TrendTileProps {
  label: string;
  value: string;
  foot?: string;
  weeks: (number | null)[];
  changedAt?: number;
  direction?: "up" | "down";
  info?: React.ReactNode;
  onOpen?: () => void;
}

export function TrendTile({ label, value, foot, weeks, changedAt, direction, info, onOpen }: TrendTileProps) {
  const [open, setOpen] = React.useState(false);
  const body = (
    <>
      <span className="trend-tile-label">{label}</span>
      <span className="trend-tile-value">
        {direction && <Icon name={direction === "up" ? "chevron-up" : "chevron-down"} label={direction === "up" ? "Subiendo" : "Bajando"} />}
        {value}
      </span>
      {foot && <span className="trend-tile-foot">{foot}</span>}
      <span className="trend-tile-line">
        <Sparkline series={weeks} label={`${label}, las últimas ${weeks.length} semanas`} marks={changedAt === undefined ? [] : [changedAt]} />
      </span>
    </>
  );
  return (
    <div className="surface trend-tile">
      {onOpen ? (
        <button type="button" className="trend-tile-body" onClick={onOpen}>
          {body}
        </button>
      ) : (
        <div className="trend-tile-body">{body}</div>
      )}
      {info && (
        <span className="trend-tile-info">
          <InfoButton label={label} open={open} onToggle={() => setOpen(!open)} />
        </span>
      )}
      {open && info && <div className="info-why trend-tile-why">{info}</div>}
    </div>
  );
}

export function TrendTiles({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <ul className="trend-tiles" aria-label={label}>
      {React.Children.map(children, (child) => (child ? <li>{child}</li> : null))}
    </ul>
  );
}
