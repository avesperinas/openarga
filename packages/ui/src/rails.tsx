import * as React from "react";

import { Icon, type IconName } from "./icons";

export interface DockBarProps {
  title: string;
  detail?: React.ReactNode;
  action: { label: string; icon?: IconName; onClick: () => void; disabled?: boolean };
}

export function DockBar({ title, detail, action }: DockBarProps) {
  return (
    <div className="dock-bar" role="region" aria-label={title}>
      <span className="dock-bar-text">
        <span className="dock-bar-title">{title}</span>
        {detail && <span className="dock-bar-detail">{detail}</span>}
      </span>
      <button type="button" className="dock-bar-action" onClick={action.onClick} disabled={action.disabled}>
        {action.icon && <Icon name={action.icon} />}
        {action.label}
      </button>
    </div>
  );
}
