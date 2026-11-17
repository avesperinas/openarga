"use client";

import { Button } from "@openarga/ui";
import * as React from "react";
import { say } from "../words";

export function DeletePageDialog({
  index,
  count,
  onResolve,
}: {
  index: number;
  count: number;
  onResolve: (keep: boolean | null) => void;
}) {
  React.useEffect(() => {
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onResolve(null);
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onResolve]);

  return (
    <div className="sheet-backdrop" onClick={() => onResolve(null)}>
      <div
        className="glass sheet sheet-narrow"
        role="dialog"
        aria-modal="true"
        aria-label={say("dashboard.page.delete", { n: index + 1 })}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="sheet-head">
          <h2 className="sheet-title">
            {say(count === 1 ? "screens.delete.one" : "screens.delete", { n: index + 1, count })}
          </h2>
        </header>
        <div className="sheet-body sheet-actions">
          <Button variant="tinted" icon="arrow-right" block onClick={() => onResolve(true)}>
            {say("screens.keep")}
          </Button>
          <Button variant="destructive" icon="trash" block onClick={() => onResolve(false)}>
            {say("screens.drop")}
          </Button>
          <Button block onClick={() => onResolve(null)}>
            {say("screens.cancel")}
          </Button>
        </div>
      </div>
    </div>
  );
}
