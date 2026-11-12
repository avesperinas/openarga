import { Icon, type IconName } from "@openarga/ui";
import * as React from "react";
import { createPortal } from "react-dom";

import type { NoteSummary } from "./api";
import { filter, fold } from "./tree";

export interface Command {
  id: string;
  label: string;
  icon: IconName;
  shortcut?: string;
  run: () => void;
}

interface Props {
  mode: "notes" | "commands";
  notes: NoteSummary[];
  commands: Command[];
  onOpen: (note: NoteSummary) => void;
  onSearch: (query: string) => void;
  onClose: () => void;
}

type Item = { key: string; label: string; detail?: string; icon: IconName; shortcut?: string; run: () => void };

export function Palette({ mode, notes, commands, onOpen, onSearch, onClose }: Props) {
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);
  const input = React.useRef<HTMLInputElement>(null);
  const list = React.useRef<HTMLUListElement>(null);

  React.useEffect(() => input.current?.focus(), []);

  const items = React.useMemo<Item[]>(() => {
    const words = fold(query.trim());
    const found = words
      ? filter(notes, query, 30)
      : [...notes].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 12);
    const noteItems: Item[] = found.map((note) => ({
      key: `n-${note.id}`,
      label: note.title,
      detail: note.folder || undefined,
      icon: "note",
      run: () => onOpen(note),
    }));
    if (mode === "notes") return noteItems;
    const commandItems: Item[] = commands
      .filter((command) => !words || fold(command.label).includes(words))
      .map((command) => ({ key: `c-${command.id}`, label: command.label, icon: command.icon, shortcut: command.shortcut, run: command.run }));
    const searchItem: Item[] = query.trim()
      ? [{ key: "search", label: `Buscar «${query.trim()}» en el texto`, icon: "search", run: () => onSearch(query.trim()) }]
      : [];
    return [...commandItems, ...noteItems, ...searchItem];
  }, [mode, notes, commands, query, onOpen, onSearch]);

  React.useEffect(() => setActive(0), [query]);
  React.useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const choose = (item: Item | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  return createPortal(
    <div className="mn-palette-scrim" onMouseDown={onClose}>
      <div
        className="glass mn-palette"
        role="dialog"
        aria-label={mode === "notes" ? "Saltar a una nota" : "Comandos"}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="mn-palette-input">
          <Icon name={mode === "notes" ? "note" : "search"} />
          <input
            ref={input}
            value={query}
            placeholder={mode === "notes" ? "Título de la nota" : "Qué quieres hacer, o una nota"}
            aria-label="Buscar"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((n) => Math.min(n + 1, items.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((n) => Math.max(n - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                choose(items[active]);
              } else if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              }
            }}
          />
        </div>
        <ul className="mn-palette-list" ref={list} role="listbox">
          {items.length === 0 && <li className="mn-palette-empty">Nada con eso.</li>}
          {items.map((item, index) => (
            <li key={item.key} role="option" aria-selected={index === active}>
              <button
                type="button"
                data-index={index}
                className="mn-palette-item"
                data-active={index === active || undefined}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(item)}
              >
                <Icon name={item.icon} />
                <span className="mn-palette-label">{item.label}</span>
                {item.detail && <span className="mn-palette-detail">{item.detail}</span>}
                {item.shortcut && <kbd className="mn-palette-key">{item.shortcut}</kbd>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>,
    document.body,
  );
}
