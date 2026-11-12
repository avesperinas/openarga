import * as React from "react";

export interface PreviewChoice<T extends string> {
  value: T;
  label: string;
  hint?: string;
  preview: React.ReactNode;
}

export function PreviewChoices<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: PreviewChoice<T>[];
  value: T;
  onChange: (value: T) => void;
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const selected = Math.max(
    options.findIndex((option) => option.value === value),
    0,
  );
  const onKeyDown = (event: React.KeyboardEvent) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (selected + step + options.length) % options.length;
    onChange(options[next]!.value);
    refs.current[next]?.focus();
  };
  return (
    <div className="preview-choices" role="radiogroup" aria-label={label} onKeyDown={onKeyDown}>
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
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            className="preview-choice"
            data-checked={checked || undefined}
            onClick={() => onChange(option.value)}
          >
            <span className="preview-choice-preview" aria-hidden="true">
              {option.preview}
            </span>
            <span className="preview-choice-label">{option.label}</span>
            {option.hint && <span className="preview-choice-hint">{option.hint}</span>}
          </button>
        );
      })}
    </div>
  );
}
