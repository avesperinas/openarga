import * as React from "react";
import { createPortal } from "react-dom";

import { Button, IconButton } from "./controls";
import { useBodyHost, useBrowserLayoutEffect, useEscape, useFocusTrap } from "./focus";
import { Icon, type IconName } from "./icons";

export interface DialogProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  actions?: { label: string; onClick: () => void; tone?: "danger"; disabled?: boolean }[];
  kind?: "dialog" | "alert";
}

export function Dialog({ title, onClose, children, actions = [], kind = "dialog" }: DialogProps) {
  const host = useBodyHost();
  const box = React.useRef<HTMLDivElement>(null);
  const titleId = React.useId();
  useFocusTrap(box, host !== null);
  useEscape(onClose);
  const dialog = (
    <div className="dialog-backdrop" onClick={kind === "alert" ? undefined : onClose}>
      <div
        ref={box}
        className="glass dialog"
        role={kind === "alert" ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="dialog-head">
          <h2 id={titleId} className="dialog-title">
            {title}
          </h2>
          <IconButton icon="close" label="Cerrar" size="small" onClick={onClose} />
        </header>
        <div className="dialog-body">{children}</div>
        {actions.length > 0 && (
          <footer className="dialog-foot">
            {actions.map((action, index) => (
              <Button
                key={action.label}
                variant={index === actions.length - 1 ? (action.tone === "danger" ? "destructive" : "primary") : "secondary"}
                onClick={action.onClick}
                disabled={action.disabled}
              >
                {action.label}
              </Button>
            ))}
          </footer>
        )}
      </div>
    </div>
  );
  return host ? createPortal(dialog, host) : dialog;
}

interface Place {
  top: number;
  left: number;
  above: boolean;
}

export function placeNear(anchor: DOMRect, size: { width: number; height: number }, viewport: { width: number; height: number }, gap = 8): Place {
  const roomBelow = viewport.height - anchor.bottom;
  const above = roomBelow < size.height + gap && anchor.top > roomBelow;
  const top = above ? Math.max(gap, anchor.top - size.height - gap) : anchor.bottom + gap;
  const left = Math.min(Math.max(gap, anchor.left), Math.max(gap, viewport.width - size.width - gap));
  return { top, left, above };
}

export interface PopoverProps {
  trigger: (props: {
    ref: React.Ref<HTMLButtonElement>;
    onClick: () => void;
    "aria-expanded": boolean;
    "aria-haspopup": "dialog" | "menu";
    "aria-controls": string;
  }) => React.ReactNode;
  children: React.ReactNode | ((close: () => void) => React.ReactNode);
  label: string;
  role?: "dialog" | "menu";
}

export function Popover({ trigger, children, label, role = "dialog" }: PopoverProps) {
  const [open, setOpen] = React.useState(false);
  const [place, setPlace] = React.useState<Place | null>(null);
  const anchor = React.useRef<HTMLButtonElement>(null);
  const box = React.useRef<HTMLDivElement>(null);
  const host = useBodyHost();
  const id = React.useId();
  const close = React.useCallback(() => setOpen(false), []);

  useBrowserLayoutEffect(() => {
    if (!open) return;
    const reposition = () => {
      if (!anchor.current || !box.current) return;
      const rect = box.current.getBoundingClientRect();
      setPlace(
        placeNear(anchor.current.getBoundingClientRect(), { width: rect.width, height: rect.height }, {
          width: window.innerWidth,
          height: window.innerHeight,
        }),
      );
    };
    reposition();
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!box.current?.contains(target) && !anchor.current?.contains(target)) close();
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open, close]);

  useEscape(close, open);
  useFocusTrap(box, open && role === "dialog" && place !== null);

  const wasOpen = React.useRef(false);
  React.useEffect(() => {
    if (wasOpen.current && !open && (document.activeElement === document.body || document.activeElement === null)) {
      anchor.current?.focus();
    }
    wasOpen.current = open;
  }, [open]);

  const content = typeof children === "function" ? children(close) : children;
  return (
    <>
      {trigger({
        ref: anchor,
        onClick: () => setOpen((now) => !now),
        "aria-expanded": open,
        "aria-haspopup": role,
        "aria-controls": id,
      })}
      {open &&
        host &&
        createPortal(
          <div
            ref={box}
            id={id}
            className="glass popover"
            role={role}
            aria-label={label}
            tabIndex={-1}
            data-above={place?.above || undefined}
            style={place ? { top: place.top, left: place.left } : { visibility: "hidden", top: 0, left: 0 }}
          >
            {content}
          </div>,
          host,
        )}
    </>
  );
}

export interface MenuItem {
  label: string;
  icon?: IconName;
  onSelect: () => void;
  tone?: "danger";
  disabled?: boolean;
}

export function Menu({ label, items, icon = "list" }: { label: string; items: MenuItem[]; icon?: IconName }) {
  return (
    <Popover
      label={label}
      role="menu"
      trigger={({ ref, ...props }) => (
        <button ref={ref} type="button" className="menu-trigger" aria-label={label} {...props}>
          <Icon name={icon} />
        </button>
      )}
    >
      {(close) => <MenuList items={items} close={close} />}
    </Popover>
  );
}

function MenuList({ items, close }: { items: MenuItem[]; close: () => void }) {
  const list = React.useRef<HTMLDivElement>(null);
  const buttons = () => Array.from(list.current?.querySelectorAll<HTMLButtonElement>("button:not([disabled])") ?? []);
  React.useEffect(() => buttons()[0]?.focus(), []);
  const move = (event: React.KeyboardEvent) => {
    const all = buttons();
    const at = all.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "ArrowDown" ? (at + 1) % all.length
      : event.key === "ArrowUp" ? (at - 1 + all.length) % all.length
      : event.key === "Home" ? 0
      : event.key === "End" ? all.length - 1
      : null;
    if (next === null) return;
    event.preventDefault();
    all[next]?.focus();
  };
  return (
    <div ref={list} className="menu" onKeyDown={move}>
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          role="menuitem"
          className="menu-item"
          data-tone={item.tone}
          disabled={item.disabled}
          onClick={() => {
            close();
            item.onSelect();
          }}
        >
          {item.icon && <Icon name={item.icon} />}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}

const TOOLTIP_DELAY_MS = 500;

export function Tooltip({ label, children }: { label: string; children: React.ReactElement<React.HTMLAttributes<HTMLElement>> }) {
  const [shown, setShown] = React.useState(false);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = React.useId();
  const show = (now = false) => {
    if (timer.current) clearTimeout(timer.current);
    if (now) setShown(true);
    else timer.current = setTimeout(() => setShown(true), TOOLTIP_DELAY_MS);
  };
  const hide = () => {
    if (timer.current) clearTimeout(timer.current);
    setShown(false);
  };
  React.useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  useEscape(hide, shown);
  return (
    <span className="tooltip-anchor" onPointerEnter={() => show()} onPointerLeave={hide} onFocus={() => show(true)} onBlur={hide}>
      {React.cloneElement(children, { "aria-describedby": shown ? id : undefined })}
      {shown && (
        <span id={id} role="tooltip" className="tooltip">
          {label}
        </span>
      )}
    </span>
  );
}
