import { IconButton } from "@openarga/ui";
import * as React from "react";
import { t } from "./lang";

export function toText(value: unknown): string {
  if (Array.isArray(value)) return value.map(toText).join(", ");
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function fromText(text: string, before: unknown): unknown {
  const clean = text.trim();
  if (Array.isArray(before)) return clean ? clean.split(",").map((part) => part.trim()).filter(Boolean) : [];
  if (typeof before === "number" && clean !== "" && Number.isFinite(Number(clean.replace(",", ".")))) {
    return Number(clean.replace(",", "."));
  }
  if (typeof before === "boolean") return /^(yes|s\u00ed|si|true|1)$/i.test(clean);
  return clean;
}

interface Props {
  values: Record<string, unknown>;
  onSet: (name: string, value: unknown) => void;
  onRemove: (name: string) => void;
  locked?: string[];
  lockedBy?: string;
}

export function Properties({ values, onSet, onRemove, locked = [], lockedBy = "" }: Props) {
  const [adding, setAdding] = React.useState({ name: "", value: "" });
  const entries = Object.entries(values);

  return (
    <div className="mn-props-form">
      {entries.map(([name, value]) =>
        locked.includes(name) ? (
          <div className="mn-prop-row" data-app="" key={name} title={t("props.locked", { app: lockedBy })}>
            <span className="mn-prop-name">{name}</span>
            <span className="mn-prop-value mn-prop-locked">{toText(value)}</span>
            <span className="mn-prop-owner">{lockedBy}</span>
          </div>
        ) : (
          <PropertyRow key={name} name={name} value={value} onSet={onSet} onRemove={onRemove} />
        ),
      )}
      <form
        className="mn-prop-row mn-prop-new"
        onSubmit={(event) => {
          event.preventDefault();
          const name = adding.name.trim();
          if (!name) return;
          onSet(name, adding.value.trim());
          setAdding({ name: "", value: "" });
        }}
      >
        <input
          className="mn-prop-name"
          value={adding.name}
          placeholder={t("props.new")}
          aria-label={t("props.new_name")}
          onChange={(event) => setAdding({ ...adding, name: event.target.value })}
        />
        <input
          className="mn-prop-value"
          value={adding.value}
          placeholder="Valor"
          aria-label={t("props.new_value")}
          onChange={(event) => setAdding({ ...adding, value: event.target.value })}
        />
        <button type="submit" className="mn-prop-add" disabled={!adding.name.trim()}>
          {t("action.add")}
        </button>
      </form>
    </div>
  );
}

function PropertyRow({
  name,
  value,
  onSet,
  onRemove,
}: {
  name: string;
  value: unknown;
  onSet: (name: string, value: unknown) => void;
  onRemove: (name: string) => void;
}) {
  const [text, setText] = React.useState(toText(value));
  React.useEffect(() => setText(toText(value)), [value]);
  const commit = () => {
    if (text !== toText(value)) onSet(name, fromText(text, value));
  };
  return (
    <div className="mn-prop-row">
      <span className="mn-prop-name">{name}</span>
      {typeof value === "boolean" ? (
        <input
          type="checkbox"
          className="mn-prop-check"
          checked={value}
          aria-label={name}
          onChange={(event) => onSet(name, event.target.checked)}
        />
      ) : (
        <input
          className="mn-prop-value"
          value={text}
          aria-label={name}
          onChange={(event) => setText(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") (event.target as HTMLInputElement).blur();
          }}
        />
      )}
      <IconButton icon="close" label={`Quitar ${name}`} variant="plain" size="small" onClick={() => onRemove(name)} />
    </div>
  );
}
