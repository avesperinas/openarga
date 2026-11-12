import * as React from "react";

import { IconButton } from "./controls";
import { Icon, type IconName } from "./icons";

export interface ToggleRowProps {
  name: string;
  detail?: string;
  tone?: number;
  checked: boolean;
  onChange: (checked: boolean) => void;
  failing?: boolean;
  action?: { icon: IconName; label: string; onClick: () => void };
}

export function ToggleRow({ name, detail, tone, checked, onChange, failing = false, action }: ToggleRowProps) {
  return (
    <li className="toggle-row" data-tone={tone} data-state={checked ? "on" : "off"} data-failing={failing || undefined}>
      <button
        type="button"
        className="toggle-row-button"
        role="switch"
        aria-checked={checked}
        aria-label={`${checked ? "Ocultar" : "Mostrar"} ${name}`}
        onClick={() => onChange(!checked)}
      >
        <span className="toggle-check" aria-hidden="true">
          <Icon name="done" />
        </span>
        <span className="toggle-row-text">
          <span className="toggle-row-name">{name}</span>
          {detail && <span className="toggle-row-detail">{detail}</span>}
        </span>
      </button>
      {action && <IconButton icon={action.icon} label={action.label} size="small" variant="plain" onClick={action.onClick} />}
    </li>
  );
}

export function ToggleList({ label, children }: { label?: string; children: React.ReactNode }) {
  return (
    <ul className="toggle-list" aria-label={label}>
      {children}
    </ul>
  );
}

export interface ToggleGroupProps {
  name: string;
  count?: string;
  tone?: number;
  state: "on" | "off" | "mixed";
  onChange: (checked: boolean) => void;
  open: boolean;
  onOpen: (open: boolean) => void;
  children: React.ReactNode;
}

export function ToggleGroup({ name, count, tone, state, onChange, open, onOpen, children }: ToggleGroupProps) {
  const id = React.useId();
  return (
    <li className="toggle-group" data-open={open || undefined} data-tone={tone}>
      <div className="toggle-group-head">
        <button type="button" className="toggle-group-open" aria-expanded={open} aria-controls={id} onClick={() => onOpen(!open)}>
          <Icon name="chevron-right" />
          <span className="toggle-group-name">{name}</span>
          {count && <span className="toggle-group-count">{count}</span>}
        </button>
        <button
          type="button"
          className="toggle-check"
          role="switch"
          data-state={state}
          aria-checked={state === "mixed" ? "mixed" : state === "on"}
          aria-label={`${state === "on" ? "Ocultar" : "Mostrar"} todo ${name}`}
          onClick={() => onChange(state !== "on")}
        >
          <Icon name={state === "mixed" ? "minus" : "done"} />
        </button>
      </div>
      {open && (
        <ul className="toggle-group-body" id={id}>
          {children}
        </ul>
      )}
    </li>
  );
}
