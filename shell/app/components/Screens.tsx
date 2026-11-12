"use client";

import { Button } from "@openarga/ui";
import * as React from "react";

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
        aria-label={`Borrar la pantalla ${index + 1}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="sheet-head">
          <h2 className="sheet-title">
            Borrar la pantalla {index + 1}, con {count} {count === 1 ? "widget" : "widgets"}
          </h2>
        </header>
        <div className="sheet-body sheet-actions">
          <Button variant="tinted" icon="arrow-right" block onClick={() => onResolve(true)}>
            Llevármelos a la pantalla de al lado
          </Button>
          <Button variant="destructive" icon="trash" block onClick={() => onResolve(false)}>
            Borrarlos con la pantalla
          </Button>
          <Button block onClick={() => onResolve(null)}>
            Cancelar
          </Button>
        </div>
      </div>
    </div>
  );
}
