import type * as React from "react";

import { TabBar, type TabItem } from "./controls";

export interface AppShellProps<T extends string> {
  label?: string;
  tabs?: TabItem<T>[];
  active?: T;
  onSelect?: (tab: T) => void;
  children: React.ReactNode;
  detail?: React.ReactNode;
  detailLabel?: string;
  fill?: boolean;
}

export function AppShell<T extends string>({
  label = "Secciones",
  tabs,
  active,
  onSelect,
  children,
  detail,
  detailLabel,
  fill,
}: AppShellProps<T>) {
  const open = detail !== undefined && detail !== null && detail !== false;
  const bare = !tabs || tabs.length === 0;
  return (
    <div className="app-shell" data-detail={open || undefined} data-bare={bare || undefined} data-fill={fill || undefined}>
      {!bare && active !== undefined && onSelect && <TabBar label={label} items={tabs} active={active} onSelect={onSelect} />}
      <div className="app-shell-main">{children}</div>
      {open && (
        <div className="app-shell-detail" role={detailLabel ? "region" : undefined} aria-label={detailLabel}>
          {detail}
        </div>
      )}
    </div>
  );
}
