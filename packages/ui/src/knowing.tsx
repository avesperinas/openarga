"use client";

import * as React from "react";

import { Button } from "./controls";
import { Icon, type IconName } from "./icons";

export type QuestionKind = "one" | "many" | "scale" | "either" | "confirm" | "free";

export interface QuestionOption {
  value: string;
  label: string;
}

export interface QuestionAnswer {
  values?: string[];
  text?: string;
  value?: string;
}

export interface QuestionCardProps {
  kind: QuestionKind;
  text: string;
  why?: string | null;
  options: QuestionOption[];
  onAnswer: (answer: QuestionAnswer) => void;
  onSkip?: () => void;
  busy?: boolean;
  eyebrow?: string;
  progress?: { done: number; total: number };
  skipLabel?: string;
}

export function QuestionCard({
  kind,
  text,
  why,
  options,
  onAnswer,
  onSkip,
  busy = false,
  eyebrow,
  progress,
  skipLabel = "Ahora no",
}: QuestionCardProps) {
  const [chosen, setChosen] = React.useState<string[]>([]);
  const [free, setFree] = React.useState("");
  const id = React.useId();
  const single = kind === "one" || kind === "either" || kind === "scale" || kind === "confirm";
  const toggle = (value: string) =>
    setChosen((now) => (now.includes(value) ? now.filter((one) => one !== value) : [...now, value]));

  return (
    <section className="question-card" aria-labelledby={`${id}-q`} aria-busy={busy || undefined}>
      {(eyebrow || progress) && (
        <div className="question-card-top">
          {eyebrow && (
            <span className="question-card-eyebrow">
              <Icon name="spark" />
              {eyebrow}
            </span>
          )}
          {progress && (
            <span className="question-card-progress" aria-label={`Pregunta ${progress.done + 1} de ${progress.total}`}>
              <span className="question-card-bar">
                <span style={{ "--done": `${(progress.done / Math.max(progress.total, 1)) * 100}%` } as React.CSSProperties} />
              </span>
              {progress.done + 1} de {progress.total}
            </span>
          )}
        </div>
      )}
      <h2 className="question-card-text" id={`${id}-q`}>
        {text}
      </h2>
      {why && <p className="question-card-why">{why}</p>}

      {kind === "free" ? (
        <textarea
          className="question-card-free"
          aria-labelledby={`${id}-q`}
          value={free}
          rows={3}
          maxLength={1000}
          onChange={(event) => setFree(event.target.value)}
        />
      ) : (
        <div className="question-card-options" data-kind={kind} role={single ? "group" : "group"}>
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              className="question-card-option"
              aria-pressed={single ? undefined : chosen.includes(option.value)}
              disabled={busy}
              onClick={() => (single ? onAnswer({ values: [option.value], value: option.value }) : toggle(option.value))}
            >
              {!single && (
                <span className="question-card-check" aria-hidden="true">
                  <Icon name="done" />
                </span>
              )}
              {option.label}
            </button>
          ))}
        </div>
      )}

      <div className="question-card-actions">
        {onSkip && (
          <Button variant="plain" onClick={onSkip} disabled={busy}>
            {skipLabel}
          </Button>
        )}
        {kind === "many" && (
          <Button variant="primary" icon="arrow-right" disabled={busy || chosen.length === 0} onClick={() => onAnswer({ values: chosen })}>
            Seguir
          </Button>
        )}
        {kind === "free" && (
          <Button variant="primary" icon="arrow-right" disabled={busy || !free.trim()} onClick={() => onAnswer({ text: free.trim() })}>
            Seguir
          </Button>
        )}
      </div>
    </section>
  );
}

const STANCES: Record<number, string> = {
  2: "Le encanta",
  1: "Le gusta",
  0: "Neutro",
  [-1]: "No le va",
  [-2]: "No quiere",
};

export function StanceDots({ stance }: { stance: number }) {
  return (
    <span className="stance-dots" data-stance={stance} role="img" aria-label={STANCES[stance] ?? ""}>
      {[-2, -1, 0, 1, 2].map((step) => (
        <span key={step} data-on={(stance > 0 && step > 0 && step <= stance) || (stance < 0 && step < 0 && step >= stance) || (stance === 0 && step === 0) || undefined} />
      ))}
    </span>
  );
}

export interface TraitRowProps {
  label: string;
  stance: number;
  source: string;
  evidence?: string | null;
  proposed: boolean;
  icon?: IconName;
  onConfirm?: () => void;
  onReject?: () => void;
  onForget?: () => void;
}

export function TraitRow({ label, stance, source, evidence, proposed, icon = "spark", onConfirm, onReject, onForget }: TraitRowProps) {
  return (
    <div className="trait-row" data-proposed={proposed || undefined} data-negative={stance < 0 || undefined}>
      <span className="trait-row-icon" aria-hidden="true">
        <Icon name={icon} />
      </span>
      <span className="trait-row-text">
        <strong>{label}</strong>
        <StanceDots stance={stance} />
        <small>
          {source}
          {evidence ? ` · ${evidence}` : ""}
        </small>
      </span>
      <span className="trait-row-actions">
        {proposed && onConfirm && (
          <button type="button" className="trait-row-button" data-tone="yes" aria-label={`Sí: ${label}`} onClick={onConfirm}>
            <Icon name="done" />
          </button>
        )}
        {proposed && onReject && (
          <button type="button" className="trait-row-button" data-tone="no" aria-label={`No: ${label}`} onClick={onReject}>
            <Icon name="close" />
          </button>
        )}
        {!proposed && onForget && (
          <button type="button" className="trait-row-button" aria-label={`Olvidar: ${label}`} onClick={onForget}>
            <Icon name="trash" />
          </button>
        )}
      </span>
    </div>
  );
}

export function ChatThread({ children }: { children: React.ReactNode }) {
  return (
    <div className="chat-thread" aria-live="polite">
      {children}
    </div>
  );
}

export function ChatBubble({ mine, sending = false, children }: { mine: boolean; sending?: boolean; children: React.ReactNode }) {
  return (
    <div className="chat-bubble" data-mine={mine || undefined} data-sending={sending || undefined}>
      {children}
    </div>
  );
}

export function ChatText({ children }: { children: string }) {
  return <p className="chat-text">{children}</p>;
}

export function Composer({
  label,
  value,
  onChange,
  onSend,
  placeholder,
  disabled = false,
  sendLabel = "Enviar",
  inputRef,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  placeholder?: string;
  disabled?: boolean;
  sendLabel?: string;
  inputRef?: React.Ref<HTMLTextAreaElement>;
}) {
  return (
    <div className="composer">
      <textarea
        ref={inputRef}
        aria-label={label}
        className="composer-input"
        value={value}
        rows={1}
        maxLength={4000}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
          event.preventDefault();
          if (!disabled && value.trim()) onSend();
        }}
      />
      <Button variant="primary" icon="arrow-right" disabled={disabled || !value.trim()} onClick={onSend}>
        {sendLabel}
      </Button>
    </div>
  );
}

export function TextAreaField({
  label,
  value,
  onChange,
  placeholder,
  rows = 6,
  max = 8000,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  max?: number;
  hint?: string;
}) {
  const id = React.useId();
  return (
    <div className="text-field">
      <label className="text-field-label" htmlFor={id}>
        {label}
      </label>
      <textarea
        id={id}
        className="text-field-input text-area-field"
        value={value}
        rows={rows}
        maxLength={max}
        placeholder={placeholder}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && (
        <p className="text-field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function ChatFab({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className="chat-fab" onClick={onClick}>
      <Icon name="note" />
      {label}
    </button>
  );
}
