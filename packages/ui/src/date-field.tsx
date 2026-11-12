"use client";

import * as React from "react";

import { MonthCalendar, isoDay } from "./calendar";
import { IconButton } from "./controls";

export interface DateFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  invalid?: boolean;
  min?: string;
  max?: string;
  autoFocus?: boolean;
  onBlur?: () => void;
}

export function spanishDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return year && month && day ? `${day}/${month}/${year}` : "";
}

export function parseSpanishDate(text: string): string | null {
  const clean = text.trim();
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(clean);
  const spanish = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/.exec(clean);
  let year: number, month: number, day: number;
  if (iso) [year, month, day] = [Number(iso[1]), Number(iso[2]), Number(iso[3])];
  else if (spanish) [day, month, year] = [Number(spanish[1]), Number(spanish[2]), Number(spanish[3])];
  else return null;
  if (year < 100) year += 2000;
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;
  return isoDay(date);
}

export function DateField({ label, value, onChange, hint, invalid = false, min, max, autoFocus, onBlur }: DateFieldProps) {
  const id = React.useId();
  const [draft, setDraft] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState(false);
  const shown = value ? new Date(`${value}T12:00:00`) : new Date();
  const [month, setMonth] = React.useState({ year: shown.getFullYear(), month: shown.getMonth() });
  const outside = (day: string) => Boolean((min && day < min) || (max && day > max));

  const toggle = () => {
    if (!open) setMonth({ year: shown.getFullYear(), month: shown.getMonth() });
    setOpen(!open);
  };
  const step = (delta: number) =>
    setMonth(({ year, month: current }) => {
      const next = new Date(year, current + delta, 1);
      return { year: next.getFullYear(), month: next.getMonth() };
    });

  return (
    <div className="text-field date-field" data-invalid={invalid || undefined}>
      <label className="text-field-label" htmlFor={id}>
        {label}
      </label>
      <div className="date-field-row">
        <input
          id={id}
          className="text-field-input"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder="dd/mm/aaaa"
          value={draft ?? spanishDate(value)}
          autoFocus={autoFocus}
          aria-invalid={invalid || undefined}
          aria-describedby={hint ? `${id}-hint` : undefined}
          onChange={(event) => {
            const text = event.target.value;
            setDraft(text);
            if (!text.trim()) return onChange("");
            const parsed = parseSpanishDate(text);
            if (parsed && !outside(parsed)) onChange(parsed);
          }}
          onBlur={() => {
            setDraft(null);
            onBlur?.();
          }}
        />
        <IconButton
          icon="calendar"
          label={open ? "Cerrar el calendario" : "Elegir en el calendario"}
          variant="plain"
          onClick={toggle}
        />
      </div>
      {open && (
        <div className="date-field-calendar">
          <MonthCalendar
            year={month.year}
            month={month.month}
            marks={{}}
            today={isoDay(new Date())}
            selected={value || null}
            disabled={outside}
            onSelect={(day) => {
              setDraft(null);
              onChange(day);
              setOpen(false);
            }}
            onPrevious={() => step(-1)}
            onNext={() => step(1)}
          />
        </div>
      )}
      {hint && (
        <p id={`${id}-hint`} className="text-field-hint">
          {hint}
        </p>
      )}
    </div>
  );
}
