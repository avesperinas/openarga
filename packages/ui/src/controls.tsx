import * as React from "react";
import { createPortal } from "react-dom";

import { useBodyHost, useEscape, useFocusTrap } from "./focus";
import { Icon, IconBadge, type IconName } from "./icons";
import { numbers } from "./regional";
import { say } from "./words";

type NativeButton = Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "className" | "style">;

export type ButtonVariant = "primary" | "secondary" | "tinted" | "plain" | "destructive";

export interface ButtonProps extends NativeButton {
  ref?: React.Ref<HTMLButtonElement>;
  variant?: ButtonVariant;
  size?: "regular" | "small";
  block?: boolean;
  icon?: IconName;
}

export function Button({
  variant = "secondary",
  size = "regular",
  block = false,
  icon,
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className="button"
      data-variant={variant}
      data-size={size === "small" ? "small" : undefined}
      data-block={block || undefined}
    >
      {icon && <Icon name={icon} />}
      {children !== undefined && <span className="button-label">{children}</span>}
    </button>
  );
}

export interface IconButtonProps extends Omit<NativeButton, "children" | "aria-label"> {
  icon: IconName;
  label: string;
  variant?: "secondary" | "plain" | "destructive";
  size?: "regular" | "small";
}

export function IconButton({
  icon,
  label,
  variant = "secondary",
  size = "regular",
  type = "button",
  ...rest
}: IconButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className="icon-button"
      aria-label={label}
      data-variant={variant}
      data-size={size === "small" ? "small" : undefined}
    >
      <Icon name={icon} />
    </button>
  );
}

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: IconName;
}

export function segmentFor(key: string, index: number, count: number): number | null {
  if (count === 0) return null;
  if (key === "ArrowRight" || key === "ArrowDown") return (index + 1) % count;
  if (key === "ArrowLeft" || key === "ArrowUp") return (index - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}

export interface SegmentedControlProps<T extends string> {
  label: string;
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  iconsWhenNarrow?: boolean;
}

export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
  iconsWhenNarrow = false,
}: SegmentedControlProps<T>) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const selected = Math.max(
    options.findIndex((option) => option.value === value),
    0,
  );

  const onKeyDown = (event: React.KeyboardEvent) => {
    const next = segmentFor(event.key, selected, options.length);
    const option = next === null ? undefined : options[next];
    if (next === null || !option) return;
    event.preventDefault();
    onChange(option.value);
    refs.current[next]?.focus();
  };

  return (
    <div
      className="segmented"
      data-icons-narrow={iconsWhenNarrow ? "" : undefined}
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      style={{ "--segments": options.length, "--selected": selected } as React.CSSProperties}
    >
      <span className="segmented-thumb" aria-hidden="true" />
      {options.map((option, index) => {
        const checked = index === selected;
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="radio"
            className="segmented-option"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(option.value)}
          >
            {option.icon && <Icon name={option.icon} />}
            <span className="segmented-label">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export interface SliderProps {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  valueText: string;
  onChange: (value: number) => void;
}

export function sliderFill(value: number, min: number, max: number): number {
  if (max <= min) return 0;
  const percent = Math.min(Math.max(((value - min) / (max - min)) * 100, 0), 100);
  return Math.round(percent * 100) / 100;
}

export function Slider({ label, min, max, step, value, valueText, onChange }: SliderProps) {
  return (
    <input
      type="range"
      className="slider"
      min={min}
      max={max}
      step={step}
      value={value}
      aria-label={label}
      aria-valuetext={valueText}
      onChange={(event) => onChange(Number(event.target.value))}
      style={{ "--fill-to": `${sliderFill(value, min, max)}%` } as React.CSSProperties}
    />
  );
}

export interface SwitchProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function Switch({ label, checked, onChange, disabled = false }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-label={label}
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-thumb" aria-hidden="true" />
    </button>
  );
}

export interface ListRowProps extends Omit<NativeButton, "children"> {
  title: string;
  subtitle?: string;
  detail?: string;
  value?: string;
  hue?: number;
  tone?: "positive" | "warning" | "negative" | "neutral";
  accessory?: IconName;
  icon?: IconName;
  image?: string;
  action?: {
    icon: IconName;
    label: string;
    onClick?: () => void;
    href?: string;
    kind?: "check" | "button";
  };
  muted?: boolean;
}

export function ListRow({
  title,
  subtitle,
  detail,
  value,
  hue,
  tone,
  accessory,
  icon,
  image,
  action,
  muted = false,
  type = "button",
  ...rest
}: ListRowProps) {
  const leading = image ? (
    <img className="list-row-image" src={image} alt="" loading="lazy" />
  ) : icon ? (
    <span className="list-row-badge">
      <IconBadge name={icon} hue={(hue ?? 8) as 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8} />
    </span>
  ) : hue !== undefined ? (
    <span className="list-row-dot" data-hue={hue} aria-hidden="true" />
  ) : tone ? (
    <span className="list-row-dot" aria-hidden="true" />
  ) : null;
  const row = (
    <button
      {...rest}
      type={type}
      className="list-row"
      data-tone={tone}
      data-muted={muted || undefined}
      data-leading={image || icon ? "" : undefined}
    >
      {leading}
      {subtitle ? (
        <span className="list-row-text">
          <span className="list-row-title">{title}</span>
          <span className="list-row-subtitle">{subtitle}</span>
        </span>
      ) : (
        <span className="list-row-title">{title}</span>
      )}
      {detail && <span className="list-row-detail">{detail}</span>}
      {value && <span className="list-row-value">{value}</span>}
      {accessory && (
        <span className="list-row-accessory">
          <Icon name={accessory} />
        </span>
      )}
    </button>
  );
  if (!action) return row;
  return (
    <div className="list-row-with-action" data-tone={tone}>
      {row}
      {action.href ? (
        <a className="list-row-action" data-kind={action.kind ?? "button"} aria-label={action.label} href={action.href}>
          <Icon name={action.icon} />
        </a>
      ) : (
        <button
          type="button"
          className="list-row-action"
          data-kind={action.kind ?? "button"}
          aria-label={action.label}
          onClick={action.onClick}
        >
          <Icon name={action.icon} />
        </button>
      )}
    </div>
  );
}

export interface CheckRowProps {
  title: string;
  detail?: string;
  checked: boolean;
  onToggle: () => void;
  more?: { label: string; onClick: () => void };
}

export function CheckRow({ title, detail, checked, onToggle, more }: CheckRowProps) {
  return (
    <div className="check-row" data-checked={checked || undefined}>
      <button type="button" role="checkbox" aria-checked={checked} className="check-row-main" onClick={onToggle}>
        <span className="check-row-box" aria-hidden="true">
          {checked && <Icon name="done" />}
        </span>
        <span className="check-row-title">{title}</span>
        {detail && <span className="check-row-detail">{detail}</span>}
      </button>
      {more && (
        <button type="button" className="check-row-more" aria-label={more.label} onClick={more.onClick}>
          <Icon name="chevron-right" />
        </button>
      )}
    </div>
  );
}

export function List({ children }: { children: React.ReactNode }) {
  return (
    <ul className="list">
      {React.Children.map(children, (child) => (child ? <li>{child}</li> : null))}
    </ul>
  );
}

const DECIMAL = () => numbers({ maximumFractionDigits: 2 });

export function formatDecimal(value: number | null): string {
  return value === null ? "—" : DECIMAL().format(value);
}

export function parseDecimal(text: string): number | null {
  const cleaned = text.trim().replace(/\s/g, "").replace(",", ".");
  if (cleaned === "") return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

export function stepValue(
  value: number | null,
  step: number,
  direction: 1 | -1,
  min = 0,
  max = Number.POSITIVE_INFINITY,
): number {
  const base = value ?? min;
  const next = value === null ? base : base + step * direction;
  const precision = Math.max(decimalsOf(step), decimalsOf(base));
  const rounded = Number(next.toFixed(precision));
  return Math.min(max, Math.max(min, rounded));
}

const decimalsOf = (n: number): number => {
  const text = String(n);
  const dot = text.indexOf(".");
  return dot === -1 ? 0 : text.length - dot - 1;
};

export interface StepperProps {
  label: string;
  value: number | null;
  step: number;
  min?: number;
  max?: number;
  unit?: string;
  inputMode?: "decimal" | "numeric";
  disabled?: boolean;
  size?: "regular" | "small";
  onChange: (value: number | null) => void;
}

export function Stepper({
  label,
  value,
  step,
  min = 0,
  max,
  unit,
  inputMode = "decimal",
  disabled = false,
  size = "regular",
  onChange,
}: StepperProps) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");

  const commit = () => {
    setEditing(false);
    const parsed = parseDecimal(draft);
    onChange(parsed === null ? null : Math.min(max ?? parsed, Math.max(min, parsed)));
  };

  return (
    <div
      className="stepper"
      role="group"
      aria-label={label}
      data-disabled={disabled || undefined}
      data-size={size === "small" ? "small" : undefined}
    >
      <button
        type="button"
        className="stepper-button"
        aria-label={say("stepper.less", { label: label.toLowerCase() })}
        disabled={disabled || (value !== null && value <= min)}
        onClick={() => onChange(stepValue(value, step, -1, min, max))}
      >
        <Icon name="minus" />
      </button>

      {editing ? (
        <input
          className="stepper-input"
          aria-label={label}
          inputMode={inputMode}
          autoFocus
          value={draft}
          onFocus={(event) => event.currentTarget.select()}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit();
            if (event.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <button
          type="button"
          className="stepper-value"
          aria-label={say("stepper.value", { label, value: `${formatDecimal(value)}${unit ? ` ${unit}` : ""}` })}
          disabled={disabled}
          onClick={() => {
            setDraft(value === null ? "" : formatDecimal(value));
            setEditing(true);
          }}
        >
          <span className="stepper-number">{formatDecimal(value)}</span>
          {unit && <span className="stepper-unit">{unit}</span>}
        </button>
      )}

      <button
        type="button"
        className="stepper-button"
        aria-label={say("stepper.more", { label: label.toLowerCase() })}
        disabled={disabled || (max !== undefined && value !== null && value >= max)}
        onClick={() => onChange(stepValue(value, step, 1, min, max))}
      >
        <Icon name="plus" />
      </button>
    </div>
  );
}

export interface ChoiceChipsProps<T extends string> {
  label: string;
  options: { value: T; label: string; disabled?: boolean }[];
  value: T | null;
  onChange: (value: T) => void;
  scroll?: boolean;
}

export function ChoiceChips<T extends string>({ label, options, value, onChange, scroll = false }: ChoiceChipsProps<T>) {
  return (
    <div className="chips" role="radiogroup" aria-label={label} data-scroll={scroll || undefined}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          className="chip"
          aria-checked={option.value === value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export interface CheckChipsProps<T extends string> {
  label: string;
  options: { value: T; label: string }[];
  values: T[];
  onChange: (values: T[]) => void;
}

export function CheckChips<T extends string>({ label, options, values, onChange }: CheckChipsProps<T>) {
  const chosen = new Set(values);
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="chip"
          aria-pressed={chosen.has(option.value)}
          onClick={() =>
            onChange(
              chosen.has(option.value)
                ? values.filter((one) => one !== option.value)
                : [...values, option.value],
            )
          }
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

export interface ElapsedProps {
  since: Date | string | null;
  label: string;
  size?: "regular" | "large";
  now?: number;
}

export function Elapsed({ since, label, size = "regular", now }: ElapsedProps) {
  const ticking = useNow();
  const current = now ?? ticking;
  const start = since === null ? null : new Date(since).getTime();
  return (
    <p className="elapsed" data-size={size === "large" ? "large" : undefined}>
      <span className="elapsed-label">{label}</span>
      <time className="elapsed-value" aria-live="off">
        {start === null ? "—" : formatElapsed(current - start)}
      </time>
    </p>
  );
}

export type SyncState = "saved" | "sending" | "pending";



export function SyncMark({ state }: { state: SyncState }) {
  return (
    <span className="sync-mark" data-state={state} role="img" aria-label={say(`sync.${state}`)}>
      {state === "saved" && <Icon name="done" />}
    </span>
  );
}

export interface BarAction {
  icon: IconName;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

export interface AppBarProps {
  title: string;
  subtitle?: string;
  back?: BarAction;
  action?: { label: string; onClick: () => void; disabled?: boolean };
}

export function AppBar({ title, subtitle, back, action }: AppBarProps) {
  return (
    <header className="glass app-bar">
      <div className="app-bar-side">
        {back && (
          <IconButton icon={back.icon} label={back.label} variant="plain" onClick={back.onClick} disabled={back.disabled} />
        )}
      </div>
      <div className="app-bar-titles">
        <h1 className="app-bar-title">{title}</h1>
        {subtitle && <p className="app-bar-subtitle">{subtitle}</p>}
      </div>
      <div className="app-bar-side" data-side="end">
        {action && (
          <Button variant="tinted" size="small" onClick={action.onClick} disabled={action.disabled}>
            {action.label}
          </Button>
        )}
      </div>
    </header>
  );
}

export interface ConfirmButtonProps extends Omit<NativeButton, "children" | "aria-label"> {
  label: string;
  confirmed?: boolean;
}

export function ConfirmButton({ label, confirmed = false, type = "button", ...rest }: ConfirmButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className="confirm-button"
      aria-label={label}
      aria-pressed={confirmed}
    >
      <Icon name="done" />
    </button>
  );
}

export interface TabItem<T extends string> {
  id: T;
  label: string;
  icon: IconName;
}

export interface TabBarProps<T extends string> {
  label: string;
  items: TabItem<T>[];
  active: T | null;
  onSelect: (id: T) => void;
}

export function TabBar<T extends string>({ label, items, active, onSelect }: TabBarProps<T>) {
  return (
    <nav className="glass tab-bar" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className="tab-bar-item"
          aria-current={item.id === active ? "page" : undefined}
          onClick={() => onSelect(item.id)}
        >
          <Icon name={item.icon} />
          <span className="tab-bar-label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}

export interface SheetProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  action?: { label: string; onClick: () => void; disabled?: boolean };
  back?: () => void;
  foot?: string;
}

export function useKeyboardInset(): number {
  const [inset, setInset] = React.useState(0);
  React.useEffect(() => {
    const viewport = typeof window === "undefined" ? undefined : window.visualViewport;
    if (!viewport) return;
    const measure = () =>
      setInset(Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop)));
    measure();
    viewport.addEventListener("resize", measure);
    viewport.addEventListener("scroll", measure);
    return () => {
      viewport.removeEventListener("resize", measure);
      viewport.removeEventListener("scroll", measure);
    };
  }, []);
  return inset;
}

const SHEET_DISMISS = 0.25;
const SHEET_FLICK = 0.6;

const canAnimate = (element: HTMLElement | null) =>
  !!element &&
  typeof element.getAnimations === "function" &&
  !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function Sheet({ title, onClose, children, action, back, foot }: SheetProps) {
  const keyboard = useKeyboardInset();
  const box = React.useRef<HTMLDivElement>(null);
  const [leaving, setLeaving] = React.useState(false);
  const [drag, setDrag] = React.useState(0);
  const start = React.useRef<{ y: number; at: number } | null>(null);

  const close = React.useCallback(() => {
    if (!canAnimate(box.current)) return onClose();
    setLeaving(true);
  }, [onClose]);

  const host = useBodyHost();
  useFocusTrap(box, host !== null);
  useEscape(close);

  const gone = React.useCallback(() => {
    onClose();
    setTimeout(() => {
      setLeaving(false);
      setDrag(0);
    }, 0);
  }, [onClose]);

  React.useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(gone, 600);
    return () => clearTimeout(timer);
  }, [leaving, gone]);

  const grab = {
    onPointerDown: (event: React.PointerEvent) => {
      if ((event.target as HTMLElement).closest("button")) return;
      start.current = { y: event.clientY, at: event.timeStamp };
      (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    },
    onPointerMove: (event: React.PointerEvent) => {
      if (start.current) setDrag(Math.max(0, event.clientY - start.current.y));
    },
    onPointerUp: (event: React.PointerEvent) => {
      if (!start.current) return;
      const moved = Math.max(0, event.clientY - start.current.y);
      const speed = moved / Math.max(1, event.timeStamp - start.current.at);
      start.current = null;
      const height = box.current?.getBoundingClientRect().height ?? Infinity;
      if (moved > height * SHEET_DISMISS || speed > SHEET_FLICK) close();
      else setDrag(0);
    },
    onPointerCancel: () => {
      start.current = null;
      setDrag(0);
    },
  };

  const sheet = (
    <div
      className="bottom-sheet-backdrop"
      data-leaving={leaving || undefined}
      data-keyboard={keyboard > 0 || undefined}
      style={keyboard > 0 ? ({ "--keyboard-inset": `${keyboard}px` } as React.CSSProperties) : undefined}
      onClick={close}
    >
      <div
        ref={box}
        className="glass bottom-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        data-leaving={leaving || undefined}
        data-dragging={drag > 0 || undefined}
        style={drag > 0 ? { "--sheet-drag": `${drag}px` } as React.CSSProperties : undefined}
        onClick={(event) => event.stopPropagation()}
        onAnimationEnd={(event) => leaving && event.target === box.current && event.animationName === "bottom-sheet-out" && gone()}
      >
        <header className="bottom-sheet-head" {...grab}>
          <span className="bottom-sheet-grabber" aria-hidden="true" />
          {back && <IconButton icon="chevron-left" label={say("sheet.back")} size="small" onClick={back} />}
          <h2 className="bottom-sheet-title">{title}</h2>
          <IconButton icon="close" label={say("sheet.close")} size="small" onClick={close} />
        </header>
        <div className="bottom-sheet-body">{children}</div>
        {action && (
          <footer className="bottom-sheet-foot">
            {foot && <p className="bottom-sheet-foot-line">{foot}</p>}
            <Button variant="primary" block onClick={action.onClick} disabled={action.disabled}>
              {action.label}
            </Button>
          </footer>
        )}
      </div>
    </div>
  );

  return host ? createPortal(sheet, host) : sheet;
}

export interface ConfirmDeleteProps {
  title: string;
  subject?: string;
  consequence?: string;
  action: string;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
}

export interface ConfirmChangeProps {
  title: string;
  changes?: { label: string; from?: string; to: string }[];
  detail?: string;
  action: string;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
}

export function ConfirmPanel({
  title,
  changes,
  detail,
  action,
  onCancel,
  onConfirm,
  titled = true,
  destructive = false,
}: ConfirmChangeProps & {
  titled?: boolean;
  destructive?: boolean;
}) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const confirm = () => {
    setBusy(true);
    setError(null);
    Promise.resolve()
      .then(onConfirm)
      .catch((reason: unknown) => {
        setError(reason instanceof Error && reason.message ? reason.message : say("confirm.save_failed"));
        setBusy(false);
      });
  };
  return (
    <div className="confirm-change" role="group" aria-label={title}>
      {titled && <p className="confirm-delete-subject">{title}</p>}
      {changes && changes.length > 0 && (
        <dl className="confirm-change-list">
          {changes.map((change, index) => (
            <React.Fragment key={index}>
              <dt>{change.label}</dt>
              <dd>
                {change.from !== undefined && (
                  <>
                    <span className="confirm-change-from">{change.from}</span>
                    <span aria-label={` ${say("confirm.becomes")} `}> → </span>
                  </>
                )}
                <span className="confirm-change-to">{change.to}</span>
              </dd>
            </React.Fragment>
          ))}
        </dl>
      )}
      {detail && <p className="confirm-delete-consequence">{detail}</p>}
      {error && (
        <p className="confirm-delete-error" role="alert">
          {error}
        </p>
      )}
      <div className="confirm-delete-actions">
        <Button variant="secondary" block onClick={onCancel} disabled={busy}>
          {say("confirm.back")}
        </Button>
        <Button
          variant={destructive ? "destructive" : "primary"}
          icon={destructive ? "trash" : undefined}
          block
          disabled={busy}
          onClick={confirm}
        >
          {busy ? (destructive ? "Borrando…" : "Guardando…") : action}
        </Button>
      </div>
    </div>
  );
}

export function ConfirmChange(props: ConfirmChangeProps) {
  return (
    <Sheet title={props.title} onClose={props.onCancel}>
      <ConfirmPanel {...props} titled={false} />
    </Sheet>
  );
}

export const cannotUndo = (): string => say("confirm.cannot_undo");

/** @deprecated Fixed at load time; use cannotUndo(). */
export const CANNOT_UNDO = cannotUndo();

export function ConfirmDelete({ title, subject, consequence, action, onCancel, onConfirm }: ConfirmDeleteProps) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const confirm = () => {
    setBusy(true);
    setError(null);
    Promise.resolve()
      .then(onConfirm)
      .catch((reason: unknown) => {
        setError(reason instanceof Error && reason.message ? reason.message : say("confirm.delete_failed"));
        setBusy(false);
      });
  };
  return (
    <Sheet title={title} onClose={busy ? () => undefined : onCancel}>
      {subject && <p className="confirm-delete-subject">{subject}</p>}
      <p className="confirm-delete-consequence">{consequence ?? cannotUndo()}</p>
      {error && (
        <p className="confirm-delete-error" role="alert">
          {error}
        </p>
      )}
      <div className="confirm-delete-actions">
        <Button variant="secondary" block onClick={onCancel} disabled={busy}>
          {say("confirm.cancel")}
        </Button>
        <Button variant="destructive" icon="trash" block disabled={busy} onClick={confirm}>
          {busy ? say("confirm.deleting") : action}
        </Button>
      </div>
    </Sheet>
  );
}

export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
  invalid?: boolean;
  type?: "text" | "search" | "time" | "password";
  inputMode?: "text" | "numeric" | "decimal";
  autoFocus?: boolean;
  onSubmit?: () => void;
  onBlur?: () => void;
  max?: string;
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  invalid = false,
  type = "text",
  inputMode,
  autoFocus,
  onSubmit,
  onBlur,
  max,
}: TextFieldProps) {
  const id = React.useId();
  return (
    <div className="text-field" data-invalid={invalid || undefined}>
      <label className="text-field-label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="text-field-input"
        type={type}
        value={value}
        placeholder={placeholder}
        inputMode={inputMode}
        autoFocus={autoFocus}
        aria-invalid={invalid || undefined}
        aria-describedby={hint ? `${id}-hint` : undefined}
        max={max}
        onBlur={onBlur}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && onSubmit) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      {hint && (
        <p id={`${id}-hint`} className="text-field-hint">
          {hint}
        </p>
      )}
    </div>
  );
}

export interface VersionTagProps {
  name: string;
  version: string;
}

export function VersionTag({ name, version }: VersionTagProps) {
  return (
    <p className="version-tag">
      <span>{name}</span>
      <span className="version-tag-number">{version}</span>
    </p>
  );
}

export interface CopyFieldProps {
  label: string;
  value: string;
  copy?: (text: string) => Promise<void>;
}

export function CopyField({ label, value, copy }: CopyFieldProps) {
  const id = React.useId();
  const [copied, setCopied] = React.useState(false);
  React.useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <div className="copy-field">
      <label className="text-field-label" htmlFor={id}>
        {label}
      </label>
      <div className="copy-field-row">
        <input
          id={id}
          className="text-field-input copy-field-value"
          readOnly
          value={value}
          onFocus={(event) => event.currentTarget.select()}
        />
        <Button
          size="small"
          icon={copied ? "done" : undefined}
          aria-label={say("copy.label", { label })}
          onClick={() => {
            const write = copy ?? ((text: string) => navigator.clipboard.writeText(text));
            void write(value).then(() => setCopied(true));
          }}
        >
          {copied ? say("copy.done") : say("copy.action")}
        </Button>
      </div>
    </div>
  );
}

export interface CredentialFieldProps {
  label: string;
  help: string;
  configured: boolean;
  hint?: string | null;
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
  onRemove?: () => void | Promise<void>;
  busy?: boolean;
  problem?: string | null;
}

export function CredentialField({
  label,
  help,
  configured,
  hint,
  value,
  onChange,
  onSave,
  onRemove,
  busy = false,
  problem = null,
}: CredentialFieldProps) {
  const placeholder = configured ? say("credential.set", { hint: hint ?? "…" }) : say("credential.paste");
  const [asking, setAsking] = React.useState(false);
  return (
    <div className="credential-field">
      <TextField
        label={label}
        type="password"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        hint={problem ?? help}
        invalid={problem !== null}
        onSubmit={value.trim() ? onSave : undefined}
      />
      <div className="credential-field-actions">
        <Button variant="primary" size="small" disabled={busy || !value.trim()} onClick={onSave}>
          {say("credential.save")}
        </Button>
        {configured && onRemove && (
          <Button variant="destructive" size="small" disabled={busy} onClick={() => setAsking(true)}>
            {say("credential.remove")}
          </Button>
        )}
      </div>
      {asking && onRemove && (
        <ConfirmDelete
          title={say("credential.remove_title", { label: `${label.charAt(0).toLowerCase()}${label.slice(1)}` })}
          subject={hint ? say("credential.ends_in", { hint: hint.replace(/^…/, "") }) : undefined}
          consequence={say("credential.remove_consequence")}
          action={say("credential.remove")}
          onCancel={() => setAsking(false)}
          onConfirm={async () => {
            await onRemove();
            setAsking(false);
          }}
        />
      )}
    </div>
  );
}

export interface LevelChipsProps<L extends string> {
  label: string;
  options: { value: string; label: string }[];
  levels: { value: L; label: string }[];
  value: Record<string, L>;
  onChange: (value: Record<string, L>) => void;
}

export function nextLevel<L extends string>(levels: { value: L }[], current: L | undefined): L | undefined {
  if (current === undefined) return levels[0]?.value;
  const index = levels.findIndex((level) => level.value === current);
  return levels[index + 1]?.value;
}

export function LevelChips<L extends string>({ label, options, levels, value, onChange }: LevelChipsProps<L>) {
  return (
    <div className="chips" role="group" aria-label={label}>
      {options.map((option) => {
        const level = value[option.value];
        const levelLabel = levels.find((candidate) => candidate.value === level)?.label;
        return (
          <button
            key={option.value}
            type="button"
            className="chip"
            data-level={level === undefined ? undefined : levels.findIndex((c) => c.value === level)}
            aria-pressed={level !== undefined}
            aria-label={levelLabel ? `${option.label}: ${levelLabel}` : option.label}
            onClick={() => {
              const next = nextLevel(levels, level);
              const rest = Object.fromEntries(Object.entries(value).filter(([key]) => key !== option.value));
              onChange(next === undefined ? rest : { ...rest, [option.value]: next });
            }}
          >
            {option.label}
            {levelLabel && <span className="chip-level">{levelLabel}</span>}
          </button>
        );
      })}
    </div>
  );
}

export interface WallpaperChoice {
  id: string;
  name: string;
  image: string;
  thumb?: string | null;
}

export interface WallpaperPickerProps {
  label: string;
  options: WallpaperChoice[];
  value: string | null;
  onChange: (id: string | null) => void;
  inherit?: WallpaperChoice;
}

export function WallpaperPicker({ label, options, value, onChange, inherit }: WallpaperPickerProps) {
  const swatch = (choice: WallpaperChoice, id: string | null) => {
    const active = value === id;
    return (
      <li key={id ?? "heredado"}>
        <button
          type="button"
          className="wallpaper-option"
          aria-pressed={active}
          data-active={active || undefined}
          style={
            { "--wallpaper-swatch": `url(${choice.thumb ?? choice.image})` } as React.CSSProperties
          }
          onClick={() => onChange(id)}
        >
          <span className="wallpaper-name">{choice.name}</span>
        </button>
      </li>
    );
  };
  return (
    <ul className="wallpaper-grid" aria-label={label}>
      {inherit && swatch(inherit, null)}
      {options.map((option) => swatch(option, option.id))}
    </ul>
  );
}

export function Skeleton({ rows = 3, label = "Cargando" }: { rows?: number; label?: string }) {
  return (
    <div className="surface skeleton" role="status" aria-label={label} aria-busy="true">
      {Array.from({ length: rows }, (_, index) => (
        <span key={index} className="skeleton-row" data-index={index % 3} />
      ))}
    </div>
  );
}
