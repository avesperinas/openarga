"use client";

import { IconButton } from "@openarga/ui";
import * as React from "react";

const STUCK_MS = 1000;

export function Overlay({
  label,
  wide,
  onClose,
  children,
}: {
  label: string;
  wide?: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const [leaving, setLeaving] = React.useState(false);

  React.useEffect(() => {
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setLeaving(true);
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  React.useEffect(() => {
    if (!leaving) return;
    const stuck = setTimeout(onClose, STUCK_MS);
    return () => clearTimeout(stuck);
  }, [leaving, onClose]);

  return (
    <div
      className="overlay"
      data-leaving={leaving || undefined}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      onClick={() => setLeaving(true)}
      onAnimationEnd={(event) => {
        if (leaving && event.target === event.currentTarget.firstElementChild) onClose();
      }}
    >
      <div className="glass overlay-panel" data-wide={wide || undefined} onClick={(event) => event.stopPropagation()}>
        <header className="overlay-head">
          <h2 className="overlay-title">{label}</h2>
          <IconButton icon="close" label="Cerrar" onClick={() => setLeaving(true)} />
        </header>
        <div className="overlay-body">{children}</div>
      </div>
    </div>
  );
}
