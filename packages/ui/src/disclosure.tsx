import * as React from "react";

import { Icon } from "./icons";

export function DisclosureList({ label, children }: { label?: string; children: React.ReactNode }) {
  return (
    <ol className="surface disclosure-list" aria-label={label}>
      {children}
    </ol>
  );
}

export interface DisclosureRowProps {
  title: string;
  subtitle?: React.ReactNode;
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  tag?: string;
  open: boolean;
  onToggle: () => void;
  children?: React.ReactNode;
}

export function DisclosureRow({ title, subtitle, leading, trailing, tag, open, onToggle, children }: DisclosureRowProps) {
  return (
    <li className="disclosure-row" data-open={open || undefined}>
      <button type="button" className="disclosure-head" aria-expanded={open} onClick={onToggle}>
        {leading}
        <span className="disclosure-titles">
          <span className="disclosure-title">
            {title}
            {tag && <span className="disclosure-tag"> · {tag}</span>}
          </span>
          {subtitle && <span className="disclosure-subtitle">{subtitle}</span>}
        </span>
        {trailing}
        <Icon name={open ? "chevron-up" : "chevron-down"} />
      </button>
      {open && children && <div className="disclosure-body">{children}</div>}
    </li>
  );
}

export function Sequence({ children }: { children: React.ReactNode }) {
  return <ol className="sequence">{children}</ol>;
}

export type SequenceState = "done" | "now" | "todo";

export interface SequenceRowProps {
  number: number;
  state: SequenceState;
  value?: React.ReactNode;
  children?: React.ReactNode;
  trailing?: React.ReactNode;
  onClick?: () => void;
  label?: string;
}

export function SequenceRow({ number, state, value, children, trailing, onClick, label }: SequenceRowProps) {
  const inner = (
    <>
      <span className="sequence-number">{number}</span>
      {value !== undefined && <span className="sequence-value">{value}</span>}
      {children}
      {trailing}
    </>
  );
  if (onClick) {
    return (
      <button type="button" className="sequence-row" data-state={state} aria-label={label} onClick={onClick}>
        {inner}
      </button>
    );
  }
  return (
    <div className="sequence-row" data-state={state} aria-label={label}>
      {inner}
    </div>
  );
}

export function SequenceSeparator({ children = "×" }: { children?: React.ReactNode }) {
  return (
    <span className="sequence-separator" aria-hidden="true">
      {children}
    </span>
  );
}

export function SequenceHint({ children }: { children: React.ReactNode }) {
  return <span className="sequence-hint">{children}</span>;
}

export function Stack({ gap = "regular", children }: { gap?: "regular" | "section"; children: React.ReactNode }) {
  return (
    <div className="stack" data-gap={gap === "section" ? "section" : undefined}>
      {children}
    </div>
  );
}

export function Inline({
  children,
  label,
  scroll,
  maxRows,
}: {
  children: React.ReactNode;
  label?: string;
  scroll?: "narrow";
  maxRows?: 1 | 2 | 3;
}) {
  return (
    <div className="inline" role={label ? "group" : undefined} aria-label={label} data-scroll={scroll} data-rows={maxRows}>
      {children}
    </div>
  );
}

export function Columns({ count = 2, stack = false, children }: { count?: 2 | 3; stack?: boolean; children: React.ReactNode }) {
  return (
    <div className="columns" data-count={count} data-stack={stack || undefined}>
      {children}
    </div>
  );
}
