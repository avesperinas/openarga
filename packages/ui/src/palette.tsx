import * as React from "react";
import { createPortal } from "react-dom";

import { useBodyHost, useEscape, useFocusTrap } from "./focus";
import { Icon, type IconName } from "./icons";

export interface PaletteItem {
  key: string;
  label: string;
  detail?: string;
  icon?: IconName;
  shortcut?: string;
  tone?: number;
  run: () => void;
}

export interface PaletteGroup {
  label: string;
  items: PaletteItem[];
}

export const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase("es");

export function matching<T extends { label: string }>(items: T[], query: string): T[] {
  const words = fold(query.trim());
  return words ? items.filter((item) => fold(item.label).includes(words)) : items;
}

export function CommandPalette({
  label,
  placeholder,
  query,
  onQuery,
  groups,
  empty = "Nada con eso.",
  onClose,
}: {
  label: string;
  placeholder: string;
  query: string;
  onQuery: (query: string) => void;
  groups: PaletteGroup[];
  empty?: string;
  onClose: () => void;
}) {
  const [active, setActive] = React.useState(0);
  const box = React.useRef<HTMLDivElement>(null);
  const list = React.useRef<HTMLUListElement>(null);
  const host = useBodyHost();
  const id = React.useId();
  useFocusTrap(box, host !== null);
  useEscape(onClose);

  const items = groups.flatMap((group) => group.items);
  React.useEffect(() => setActive(0), [query, items.length]);
  React.useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  const choose = (item: PaletteItem | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  let index = -1;
  const palette = (
    <div className="palette-backdrop" onClick={onClose}>
      <div ref={box} className="glass palette" role="dialog" aria-modal="true" aria-label={label} onClick={(event) => event.stopPropagation()}>
        <div className="palette-field">
          <Icon name="search" />
          <input
            autoFocus
            className="palette-input"
            value={query}
            placeholder={placeholder}
            aria-label={label}
            role="combobox"
            aria-expanded="true"
            aria-controls={`${id}-list`}
            aria-activedescendant={items[active] ? `${id}-${active}` : undefined}
            onChange={(event) => onQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActive((at) => Math.min(items.length - 1, at + 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((at) => Math.max(0, at - 1));
              } else if (event.key === "Enter") {
                event.preventDefault();
                choose(items[active]);
              }
            }}
          />
          <kbd className="palette-key">esc</kbd>
        </div>
        <ul id={`${id}-list`} ref={list} className="palette-list" role="listbox" aria-label={label}>
          {items.length === 0 && (
            <li className="palette-empty" role="presentation">
              {empty}
            </li>
          )}
          {groups.map(
            (group) =>
              group.items.length > 0 && (
                <React.Fragment key={group.label}>
                  <li className="palette-group" role="presentation">
                    {group.label}
                  </li>
                  {group.items.map((item) => {
                    index += 1;
                    const mine = index;
                    return (
                      <li
                        key={item.key}
                        id={`${id}-${mine}`}
                        data-index={mine}
                        role="option"
                        aria-selected={active === mine}
                        className="palette-item"
                        data-tone={item.tone}
                        onPointerMove={() => setActive(mine)}
                        onClick={() => choose(item)}
                      >
                        {item.tone !== undefined && <span className="tone-dot" aria-hidden="true" />}
                        {item.icon && <Icon name={item.icon} />}
                        <span className="palette-text">
                          <span className="palette-label">{item.label}</span>
                          {item.detail && <span className="palette-detail">{item.detail}</span>}
                        </span>
                        {item.shortcut && <kbd className="palette-key">{item.shortcut}</kbd>}
                      </li>
                    );
                  })}
                </React.Fragment>
              ),
          )}
        </ul>
      </div>
    </div>
  );
  return host ? createPortal(palette, host) : palette;
}

export function useShortcut(key: string, onOpen: () => void): void {
  const latest = React.useRef(onOpen);
  latest.current = onOpen;
  React.useEffect(() => {
    const listen = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === key.toLowerCase()) {
        event.preventDefault();
        latest.current();
      }
    };
    window.addEventListener("keydown", listen);
    return () => window.removeEventListener("keydown", listen);
  }, [key]);
}
