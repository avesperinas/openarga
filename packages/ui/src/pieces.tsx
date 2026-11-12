import * as React from "react";

import { DateField } from "./date-field";
import { Icon } from "./icons";

const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase("es");

export interface ScreenTab<T extends string> {
  id: T;
  label: string;
  count?: number;
}

export function Tabs<T extends string>({
  label,
  items,
  active,
  onSelect,
}: {
  label: string;
  items: ScreenTab<T>[];
  active: T;
  onSelect: (id: T) => void;
}) {
  const list = React.useRef<HTMLDivElement>(null);
  const move = (event: React.KeyboardEvent) => {
    const at = items.findIndex((item) => item.id === active);
    const next =
      event.key === "ArrowRight" ? (at + 1) % items.length
      : event.key === "ArrowLeft" ? (at - 1 + items.length) % items.length
      : event.key === "Home" ? 0
      : event.key === "End" ? items.length - 1
      : null;
    if (next === null) return;
    event.preventDefault();
    onSelect(items[next]!.id);
    list.current?.querySelectorAll<HTMLButtonElement>("[role=tab]")[next]?.focus();
  };
  return (
    <div ref={list} className="tabs" role="tablist" aria-label={label} onKeyDown={move}>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          className="tabs-tab"
          aria-selected={item.id === active}
          tabIndex={item.id === active ? 0 : -1}
          onClick={() => onSelect(item.id)}
        >
          {item.label}
          {item.count !== undefined && <Badge>{item.count}</Badge>}
        </button>
      ))}
    </div>
  );
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0]!.charAt(0);
  const last = words.length > 1 ? words[words.length - 1]!.charAt(0) : "";
  return (first + last).toLocaleUpperCase("es");
}

export function toneOf(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return (hash % 8) + 1;
}

export function Avatar({ name, src, size = "m" }: { name: string; src?: string | null; size?: "s" | "m" | "l" }) {
  return (
    <span className="avatar" data-size={size} data-hue={toneOf(name)} role="img" aria-label={name}>
      {src ? <img src={src} alt="" loading="lazy" decoding="async" /> : <span aria-hidden="true">{initials(name)}</span>}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "accent" | "warning" | "positive" | "negative";
}) {
  return (
    <span className="badge" data-tone={tone}>
      {children}
    </span>
  );
}

export interface ComboboxOption {
  value: string;
  label: string;
  detail?: string;
}

export function Combobox({
  label,
  options,
  value,
  onChange,
  placeholder,
  create,
  limit = 8,
}: {
  label: string;
  options: ComboboxOption[];
  value: string | null;
  onChange: (value: string) => void;
  placeholder?: string;
  create?: (text: string) => string;
  limit?: number;
}) {
  const chosen = options.find((option) => option.value === value) ?? null;
  const [text, setText] = React.useState(chosen?.label ?? "");
  const [open, setOpen] = React.useState(false);
  const [active, setActive] = React.useState(0);
  const id = React.useId();

  React.useEffect(() => {
    if (chosen) setText(chosen.label);
  }, [chosen]);

  const typed = text.trim();
  const found = React.useMemo(() => {
    const wanted = fold(typed);
    return options.filter((option) => !wanted || fold(option.label).includes(wanted)).slice(0, limit);
  }, [options, typed, limit]);
  const offerNew = create && typed && !options.some((option) => fold(option.label) === fold(typed));
  const total = found.length + (offerNew ? 1 : 0);

  const pick = (index: number) => {
    if (index < found.length) {
      onChange(found[index]!.value);
      setText(found[index]!.label);
    } else if (offerNew) {
      onChange(typed);
    }
    setOpen(false);
  };

  return (
    <div className="text-field combobox">
      <label className="text-field-label" htmlFor={`${id}-input`}>
        {label}
      </label>
      <input
        id={`${id}-input`}
        className="text-field-input"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={open && total > 0 ? `${id}-${active}` : undefined}
        autoComplete="off"
        value={text}
        placeholder={placeholder}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActive((at) => Math.min(total - 1, at + 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((at) => Math.max(0, at - 1));
          } else if (event.key === "Enter" && open && total > 0) {
            event.preventDefault();
            pick(active);
          } else if (event.key === "Escape" && open) {
            event.stopPropagation();
            setText(chosen?.label ?? "");
            setOpen(false);
          }
        }}
      />
      {open && total > 0 && (
        <ul id={`${id}-list`} className="glass combobox-list" role="listbox" aria-label={label}>
          {found.map((option, index) => (
            <li
              key={option.value}
              id={`${id}-${index}`}
              role="option"
              aria-selected={index === active}
              className="combobox-option"
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => pick(index)}
              onPointerEnter={() => setActive(index)}
            >
              <span>{option.label}</span>
              {option.detail && <span className="combobox-detail">{option.detail}</span>}
            </li>
          ))}
          {offerNew && (
            <li
              id={`${id}-${found.length}`}
              role="option"
              aria-selected={active === found.length}
              className="combobox-option"
              data-new
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => pick(found.length)}
              onPointerEnter={() => setActive(found.length)}
            >
              <Icon name="plus" />
              <span>{create!(typed)}</span>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

export function FileField({
  label,
  accept,
  multiple = false,
  hint,
  onFiles,
}: {
  label: string;
  accept?: string;
  multiple?: boolean;
  hint?: string;
  onFiles: (files: File[]) => void;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const id = React.useId();
  return (
    <div
      className="file-field"
      data-over={over || undefined}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        const files = Array.from(event.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
    >
      <input
        ref={input}
        id={id}
        type="file"
        className="file-field-input"
        accept={accept}
        multiple={multiple}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) onFiles(files);
          event.target.value = "";
        }}
      />
      <label htmlFor={id} className="file-field-button">
        <Icon name="clip" />
        {label}
      </label>
      {hint && (
        <span id={`${id}-hint`} className="file-field-hint">
          {hint}
        </span>
      )}
    </div>
  );
}

export interface DateRange {
  from: string;
  to: string;
}

export function rangeProblem({ from, to }: DateRange): string | null {
  if (from && to && to < from) return "El final va antes del principio.";
  return null;
}

export function DateRangeField({
  label,
  value,
  onChange,
  min,
  max,
}: {
  label: string;
  value: DateRange;
  onChange: (value: DateRange) => void;
  min?: string;
  max?: string;
}) {
  const problem = rangeProblem(value);
  return (
    <fieldset className="date-range">
      <legend className="text-field-label">{label}</legend>
      <div className="date-range-fields">
        <DateField label="Desde" value={value.from} min={min} max={value.to || max} onChange={(from) => onChange({ ...value, from })} />
        <DateField
          label="Hasta"
          value={value.to}
          min={value.from || min}
          max={max}
          invalid={problem !== null}
          hint={problem ?? undefined}
          onChange={(to) => onChange({ ...value, to })}
        />
      </div>
    </fieldset>
  );
}
