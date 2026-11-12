import * as React from "react";

import { Icon } from "./icons";

export function StepList({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <ol className="surface step-list" aria-label={label}>
      {children}
    </ol>
  );
}

export interface StepItemProps {
  number: number;
  text: string;
  when?: string;
  detail?: string;
  done: boolean;
  next?: boolean;
  onToggle: () => void;
}

export function StepItem({ number, text, when, detail, done, next = false, onToggle }: StepItemProps) {
  return (
    <li>
      <button
        type="button"
        className="step-item"
        data-state={done ? "done" : next ? "next" : "todo"}
        aria-pressed={done}
        onClick={onToggle}
      >
        <span className="step-item-number" aria-hidden="true">
          {done ? <Icon name="done" /> : number}
        </span>
        <span className="step-item-body">
          {when && <span className="step-item-when">{when}</span>}
          <span className="step-item-text">{text}</span>
          {detail && <span className="step-item-detail">{detail}</span>}
        </span>
      </button>
    </li>
  );
}
