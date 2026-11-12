import * as React from "react";

export function Panes({
  main,
  aside,
  asideLabel,
  asideFirst = false,
}: {
  main: React.ReactNode;
  aside: React.ReactNode;
  asideLabel: string;
  asideFirst?: boolean;
}) {
  return (
    <div className="panes" data-aside-first={asideFirst || undefined}>
      <div className="panes-main">{main}</div>
      <aside className="panes-aside" aria-label={asideLabel}>
        {aside}
      </aside>
    </div>
  );
}
