"use client";

import { IconButton, List, ListRow } from "@openarga/ui";
import * as React from "react";

import type { CatalogueEntry, WidgetChoice } from "../lib/kernel";
import type { AreaKey } from "../lib/panels";
import { request } from "../lib/session";

const GROUP_NAMES: Record<string, string> = { panel: "Paneles del inicio", kernel: "Sistema" };

export function AddSheet({
  catalogue,
  placed,
  panels = [],
  onPanel,
  onPick,
  onClose,
}: {
  catalogue: CatalogueEntry[];
  placed: Set<string>;
  panels?: { key: AreaKey; label: string; hue: number }[];
  onPanel?: (area: AreaKey) => void;
  onPick: (entry: CatalogueEntry, option?: string) => void;
  onClose: () => void;
}) {
  const [choosing, setChoosing] = React.useState<CatalogueEntry | null>(null);
  const [choices, setChoices] = React.useState<WidgetChoice[] | null>(null);
  const [failed, setFailed] = React.useState(false);

  const pick = (entry: CatalogueEntry) => {
    if (!entry.option) {
      onPick(entry);
      return;
    }
    setChoosing(entry);
    setChoices(null);
    setFailed(false);
    request(entry.option.endpoint, { headers: { accept: "application/json" } })
      .then((response) => (response.ok ? (response.json() as Promise<WidgetChoice[]>) : Promise.reject()))
      .then(setChoices, () => setFailed(true));
  };

  const groups = new Map<string, CatalogueEntry[]>();
  for (const entry of catalogue) {
    groups.set(entry.source, [...(groups.get(entry.source) ?? []), entry]);
  }

  React.useEffect(() => {
    const escape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [onClose]);

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="glass sheet"
        role="dialog"
        aria-modal="true"
        aria-label="Añadir widget"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="sheet-head">
          {choosing && <IconButton icon="chevron-left" label="Volver a los widgets" onClick={() => setChoosing(null)} />}
          <h2 className="sheet-title">{choosing ? `${choosing.title}: ${choosing.option?.label.toLowerCase()}` : "Añadir widget"}</h2>
          <IconButton icon="close" label="Cerrar" onClick={onClose} />
        </header>

        {choosing ? (
          <div className="sheet-body">
            {failed && <p className="sheet-group">No se han podido cargar las opciones.</p>}
            {!failed && choices === null && <p className="sheet-group">Cargando…</p>}
            {choices !== null && choices.length === 0 && <p className="sheet-group">No hay nada que elegir todavía.</p>}
            {choices && choices.length > 0 && (
              <List>
                {choices.map((choice) => (
                  <ListRow
                    key={choice.value}
                    title={choice.label}
                    hue={choosing.hue}
                    accessory="plus"
                    onClick={() => onPick(choosing, choice.value)}
                  />
                ))}
              </List>
            )}
          </div>
        ) : (
        <div className="sheet-body">
          {panels.length > 0 && onPanel && (
            <section>
              <h3 className="sheet-group">Paneles</h3>
              <List>
                {panels.map((panel) => (
                  <ListRow
                    key={panel.key}
                    title={panel.label}
                    detail="Una página con lo de todas sus apps"
                    hue={panel.hue}
                    accessory="plus"
                    onClick={() => onPanel(panel.key)}
                  />
                ))}
              </List>
            </section>
          )}
          {[...groups].map(([source, entries]) => (
            <section key={source}>
              <h3 className="sheet-group">{GROUP_NAMES[source] ?? source}</h3>
              <List>
                {entries.map((entry) => {
                  const already = !entry.option && placed.has(`${entry.source}/${entry.id}`);
                  return (
                    <ListRow
                      key={`${entry.source}/${entry.id}`}
                      title={entry.title}
                      detail={already ? "Ya colocado" : entry.option ? `Eliges ${entry.option.label.toLowerCase()}` : entry.sizes.join(" · ")}
                      hue={entry.hue}
                      accessory={already ? "done" : "plus"}
                      disabled={already}
                      onClick={() => pick(entry)}
                    />
                  );
                })}
              </List>
            </section>
          ))}
        </div>
        )}
      </div>
    </div>
  );
}
