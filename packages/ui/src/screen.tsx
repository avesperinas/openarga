"use client";

import * as React from "react";

import { Button, IconButton } from "./controls";
import { Icon, IconBadge, type IconName } from "./icons";
import { Menu, type MenuItem } from "./overlays";
import type { Hue } from "./Widget";
import { say } from "./words";

export function Screen({
  children,
  wide = false,
  label,
}: {
  children: React.ReactNode;
  wide?: boolean;
  label?: string;
}) {
  return (
    <main className="screen" data-wide={wide || undefined} aria-label={label}>
      {children}
    </main>
  );
}

export interface SectionAction {
  label: string;
  onClick: () => void;
  icon?: IconName;
}

export function Section({
  title,
  count,
  tone,
  action,
  menu,
  children,
}: {
  title?: string;
  count?: number;
  tone?: "warning" | "negative";
  action?: SectionAction;
  menu?: { label: string; items: MenuItem[] };
  children: React.ReactNode;
}) {
  return (
    <section className="section" data-tone={tone}>
      {(title || action || menu) && (
        <header className="section-head">
          {title && (
            <h2 className="section-title">
              {title}
              {count !== undefined && <span className="section-count">{count}</span>}
            </h2>
          )}
          {action && (
            <button type="button" className="section-action" onClick={action.onClick}>
              {action.icon && <Icon name={action.icon} />}
              {action.label}
            </button>
          )}
          {menu && <Menu label={menu.label} items={menu.items} icon="more" />}
        </header>
      )}
      {children}
    </section>
  );
}

export function GroupLabel({
  children,
  count,
  tone,
}: {
  children: React.ReactNode;
  count?: number;
  tone?: "warning" | "negative";
}) {
  return (
    <h2 className="group-label" data-tone={tone}>
      {children}
      {count !== undefined && <span className="group-label-count">{count}</span>}
    </h2>
  );
}

export function Card({
  children,
  onClick,
  href,
  label,
  flush = false,
  title,
  action,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  href?: string;
  label?: string;
  flush?: boolean;
  title?: string;
  action?: { icon: IconName; label: string; onClick: () => void };
}) {
  if (title) {
    return (
      <section className="surface card" data-flush={flush || undefined} aria-label={title}>
        <header className="card-head">
          <h2 className="card-title">{title}</h2>
          {action && <IconButton icon={action.icon} label={action.label} size="small" onClick={action.onClick} />}
        </header>
        {children}
      </section>
    );
  }
  const props = { className: "surface card", "data-flush": flush || undefined, "aria-label": label };
  if (href) {
    return (
      <a {...props} href={href} data-pressable="">
        {children}
      </a>
    );
  }
  if (onClick) {
    return (
      <button {...props} type="button" onClick={onClick} data-pressable="">
        {children}
      </button>
    );
  }
  return <div {...props}>{children}</div>;
}

export function EmptyState({
  icon,
  hue = 8,
  title,
  children,
  action,
}: {
  icon?: IconName;
  hue?: Hue;
  title: string;
  children?: React.ReactNode;
  action?: { label: string; onClick: () => void; icon?: IconName };
}) {
  return (
    <div className="surface empty-state">
      {icon && <IconBadge name={icon} hue={hue} />}
      <p className="empty-state-title">{title}</p>
      {children && <div className="empty-state-body">{children}</div>}
      {action && (
        <Button variant="tinted" icon={action.icon} onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

export type NoticeTone = "info" | "positive" | "warning" | "negative";

const NOTICE_ICON: Record<NoticeTone, IconName> = {
  info: "info",
  positive: "done",
  warning: "alert",
  negative: "alert",
};

export function Notice({
  tone = "info",
  title,
  children,
  action,
}: {
  tone?: NoticeTone;
  title?: string;
  children?: React.ReactNode;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="notice" data-tone={tone} role={tone === "negative" ? "alert" : "status"}>
      <span className="notice-icon" aria-hidden="true">
        <Icon name={NOTICE_ICON[tone]} />
      </span>
      <div className="notice-text">
        {title && <p className="notice-title">{title}</p>}
        {children && <div className="notice-body">{children}</div>}
      </div>
      {action && (
        <button type="button" className="notice-action" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}

export function CreateButton({
  label,
  onClick,
  icon = "plus",
}: {
  label: string;
  onClick: () => void;
  icon?: IconName;
}) {
  return (
    <button type="button" className="create-button" onClick={onClick}>
      <Icon name={icon} />
      {label}
    </button>
  );
}

export interface Toast {
  message: string;
  action?: { label: string; run: () => void };
  tone?: "error";
}

const ToastContext = React.createContext<(toast: Toast) => void>(() => undefined);

export const useToast = () => React.useContext(ToastContext);

export function ToastHost({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = React.useState<(Toast & { id: number }) | null>(null);
  const counter = React.useRef(0);
  const show = React.useCallback((next: Toast) => {
    counter.current += 1;
    setToast({ ...next, id: counter.current });
  }, []);
  React.useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), toast.tone === "error" || toast.action ? 6000 : 2800);
    return () => clearTimeout(timer);
  }, [toast]);
  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toast-host" aria-live="polite">
        {toast && (
          <div key={toast.id} className="glass toast" role="status" data-tone={toast.tone}>
            <span className="toast-text">{toast.message}</span>
            {toast.action && (
              <button
                type="button"
                className="toast-action"
                onClick={() => {
                  toast.action?.run();
                  setToast(null);
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder,
  label,
  busy = false,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label: string;
  busy?: boolean;
  autoFocus?: boolean;
}) {
  return (
    <label className="search-field" data-busy={busy || undefined} aria-busy={busy || undefined}>
      <Icon name="search" />
      <input
        type="search"
        placeholder={placeholder}
        value={value}
        enterKeyHint="search"
        aria-label={label}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
      />
      {value && (
        <button type="button" className="search-field-clear" aria-label={say("search.clear")} onClick={() => onChange("")}>
          <Icon name="close" />
        </button>
      )}
    </label>
  );
}

export function Hint({
  children,
  tone,
  announce = false,
  lines = false,
}: {
  children: React.ReactNode;
  tone?: "warning";
  announce?: boolean;
  lines?: boolean;
}) {
  return (
    <p className="hint" data-tone={tone} data-lines={lines || undefined} role={tone ? "alert" : announce ? "status" : undefined}>
      {children}
    </p>
  );
}

export function Heading({
  children,
  count,
  id,
}: {
  children: React.ReactNode;
  count?: number;
  id?: string;
}) {
  return (
    <h2 className="section-title" id={id}>
      {children}
      {count !== undefined && <span className="section-count">{count}</span>}
    </h2>
  );
}
