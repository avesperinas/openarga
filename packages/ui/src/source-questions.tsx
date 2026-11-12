"use client";

import * as React from "react";

import { TONES, type Tone } from "./calendar-layout";
import { CheckChips, ChoiceChips, List, ListRow, TextField } from "./controls";

export interface SourceChoice {
  code: string;
  name: string;
  [carried: string]: unknown;
}

export interface SourceAsk {
  key: string;
  kind: string;
  label: string;
  source: string | null;
  depends_on: string | null;
  optional: boolean;
  none_label: string | null;
  default: string | null;
  choices: { value: string; label: string }[];
  defaults: string[];
  carries: [string, string][];
  placeholder: string;
  help: string;
  display?: string | null;
}

export interface InletSetting {
  key: string;
  kind: "text" | "tone" | "choice" | string;
  label: string;
  default?: string | number | null;
  choices?: { value: string; label: string }[];
}

export type SourceAnswer = { choice?: SourceChoice | null; values?: string[]; text?: string };
export type SourceAnswers = Record<string, SourceAnswer>;
export type InletValues = Record<string, string | number>;

export interface SourceSearchResult {
  results: SourceChoice[];
  failed: string | null;
}

export type SourceSearch = (ask: string, query?: string, parent?: string) => Promise<SourceSearchResult>;

const NONE = "__none__";
const MANY = 12;

export function sourceParams(asks: SourceAsk[], answers: SourceAnswers): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  for (const ask of asks) {
    const answer = answers[ask.key] ?? {};
    if (ask.kind === "checks") params[ask.key] = answer.values ?? ask.defaults;
    else if (ask.kind === "url") params[ask.key] = (answer.text ?? "").trim();
    else {
      params[ask.key] = answer.choice?.code ?? null;
      for (const [field, target] of ask.carries) {
        const carried = answer.choice?.[field];
        if (carried !== undefined) params[target] = carried;
      }
    }
  }
  return params;
}

export function sourceMissing(asks: SourceAsk[], answers: SourceAnswers): string | null {
  for (const ask of asks) {
    const answer = answers[ask.key] ?? {};
    if (ask.kind === "checks" && (answer.values ?? ask.defaults).length === 0) return `Elige al menos una: ${ask.label.toLowerCase()}.`;
    if (ask.kind === "url" && !(answer.text ?? "").trim()) return `Falta: ${ask.label.toLowerCase()}.`;
    if ((ask.kind === "lookup" || ask.kind === "pick") && !ask.optional && !answer.choice) return `Elige: ${ask.label.toLowerCase()}.`;
  }
  return null;
}

function host(url: string): string {
  try {
    return new URL(url.trim().replace(/^webcal:\/\//i, "https://")).host.replace(/^www\./, "");
  } catch {
    return "";
  }
}

export function proposedSourceName(source: { name: string; title: string; asks: SourceAsk[] }, answers: SourceAnswers): string {
  const label = (key: string): string => {
    const ask = source.asks.find((one) => one.key === key);
    const answer = answers[key];
    if (!ask || !answer) return "";
    if (ask.kind === "url") return host(answer.text ?? "");
    return answer.choice?.name ?? "";
  };
  const filled = source.name.replace(/\{([^}]+)\}/g, (_, keys: string) => keys.split("|").map(label).find(Boolean) ?? "");
  return filled.replace(/\s*·\s*$/, "").trim() || source.title;
}

export function countryName(code: string, fallback: string): string {
  try {
    return new Intl.DisplayNames(["es"], { type: "region" }).of(code) ?? fallback;
  } catch {
    return fallback;
  }
}

export function inletValues(settings: InletSetting[], values: InletValues, name: string, tone: number): InletValues {
  const out: InletValues = {};
  for (const setting of settings) {
    const given = values[setting.key];
    if (given !== undefined) out[setting.key] = given;
    else if (setting.kind === "text") out[setting.key] = (setting.default as string | undefined) ?? name;
    else if (setting.kind === "tone") out[setting.key] = (setting.default as number | undefined) ?? tone;
    else if (setting.default !== undefined && setting.default !== null) out[setting.key] = setting.default;
  }
  return out;
}

export interface SourceQuestionsProps {
  asks: SourceAsk[];
  answers: SourceAnswers;
  onChange: (answers: SourceAnswers) => void;
  search: SourceSearch;
  onError: (message: string | null) => void;
}

export function SourceQuestions({ asks, answers, onChange, search, onError }: SourceQuestionsProps) {
  const latest = React.useRef(answers);
  latest.current = answers;
  return (
    <>
      {asks.map((ask) => (
        <Question
          key={ask.key}
          ask={ask}
          value={answers[ask.key] ?? {}}
          parent={ask.depends_on ? (answers[ask.depends_on]?.choice ?? null) : null}
          onChange={(value) => onChange({ ...latest.current, [ask.key]: value })}
          search={search}
          onError={onError}
        />
      ))}
    </>
  );
}

export interface InletSettingsProps {
  settings: InletSetting[];
  values: InletValues;
  onChange: (values: InletValues) => void;
  title?: string;
}

export function InletSettings({ settings, values, onChange, title }: InletSettingsProps) {
  if (settings.length === 0) return null;
  const set = (key: string, value: string | number) => onChange({ ...values, [key]: value });
  return (
    <div className="source-inlet" aria-label={title}>
      {title && <span className="source-label">{title}</span>}
      {settings.map((setting) => {
        const value = values[setting.key];
        if (setting.kind === "text") {
          return <TextField key={setting.key} label={setting.label} value={String(value ?? "")} onChange={(text) => set(setting.key, text)} />;
        }
        if (setting.kind === "tone") {
          return (
            <div key={setting.key} className="source-field">
              <span className="source-label">{setting.label}</span>
              <div className="source-tones" role="radiogroup" aria-label={setting.label}>
                {TONES.map((one) => (
                  <button
                    key={one.tone}
                    type="button"
                    role="radio"
                    aria-checked={value === one.tone}
                    aria-label={one.name}
                    title={one.name}
                    className="source-tone"
                    data-tone={one.tone}
                    onClick={() => set(setting.key, one.tone as Tone)}
                  />
                ))}
              </div>
            </div>
          );
        }
        if (setting.kind === "choice") {
          return (
            <div key={setting.key} className="source-field">
              <span className="source-label">{setting.label}</span>
              <ChoiceChips label={setting.label} options={setting.choices ?? []} value={String(value ?? "")} onChange={(chosen) => set(setting.key, chosen)} />
            </div>
          );
        }
        return (
          <p key={setting.key} className="source-note">
            «{setting.label}» se elige en una versión más nueva.
          </p>
        );
      })}
    </div>
  );
}

function Question({
  ask,
  value,
  parent,
  onChange,
  search,
  onError,
}: {
  ask: SourceAsk;
  value: SourceAnswer;
  parent: SourceChoice | null;
  onChange: (value: SourceAnswer) => void;
  search: SourceSearch;
  onError: (message: string | null) => void;
}) {
  const [query, setQuery] = React.useState("");
  const [options, setOptions] = React.useState<SourceChoice[] | null>(ask.kind === "pick" ? null : []);
  const change = React.useRef(onChange);
  change.current = onChange;
  const find = React.useRef(search);
  find.current = search;

  React.useEffect(() => {
    if (ask.kind !== "pick") return;
    if (ask.depends_on && !parent) {
      setOptions([]);
      return;
    }
    let alive = true;
    setOptions(null);
    find
      .current(ask.key, undefined, ask.depends_on ? parent?.code : undefined)
      .then((found) => {
        if (!alive) return;
        if (found.failed) onError(`No se puede leer: ${found.failed}`);
        const named =
          ask.display === "country"
            ? found.results.map((one) => ({ ...one, name: countryName(one.code, one.name) })).sort((a, b) => a.name.localeCompare(b.name, "es"))
            : found.results;
        setOptions(named);
        change.current({ choice: named.find((one) => one.code === ask.default) ?? null });
      })
      .catch(() => alive && setOptions([]));
    return () => {
      alive = false;
    };
  }, [ask, parent, onError]);

  React.useEffect(() => {
    if (ask.kind !== "lookup" || query.trim().length < 2) {
      if (ask.kind === "lookup") setOptions([]);
      return;
    }
    let alive = true;
    const timer = setTimeout(() => {
      find
        .current(ask.key, query.trim())
        .then((found) => {
          if (!alive) return;
          setOptions(found.results);
          onError(found.failed ? `No se puede buscar: ${found.failed}` : null);
        })
        .catch((failure: unknown) => alive && onError(failure instanceof Error ? failure.message : String(failure)));
    }, 300);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [ask, query, onError]);

  const chosen = value.choice ?? null;
  const label = `${ask.label}${chosen ? `: ${chosen.name}` : ""}`;

  if (ask.kind === "checks") {
    return (
      <div className="source-field">
        <span className="source-label">{ask.label}</span>
        <CheckChips label={ask.label} options={ask.choices} values={value.values ?? ask.defaults} onChange={(values) => onChange({ values })} />
        {ask.help && <p className="source-note">{ask.help}</p>}
      </div>
    );
  }
  if (ask.kind === "url") {
    return <TextField label={ask.label} value={value.text ?? ""} placeholder={ask.placeholder} autoFocus onChange={(text) => onChange({ text })} hint={ask.help || undefined} />;
  }
  if (ask.kind === "lookup") {
    return (
      <div className="source-field">
        <span className="source-label">{label}</span>
        <TextField label={`Buscar ${ask.label.toLowerCase()}`} type="search" value={query} placeholder={ask.placeholder} autoFocus onChange={setQuery} />
        {(options ?? []).length > 0 && (
          <List>
            {(options ?? []).map((one, index) => (
              <ListRow
                key={`${index}:${one.code}`}
                title={one.name}
                value={typeof one.detail === "string" ? one.detail : undefined}
                onClick={() => {
                  onChange({ choice: one });
                  setQuery("");
                }}
              />
            ))}
          </List>
        )}
        {ask.help && <p className="source-note">{ask.help}</p>}
      </div>
    );
  }
  if (ask.kind !== "pick") {
    return <p className="source-note">«{ask.label}» se elige en una versión más nueva.</p>;
  }
  const all = options ?? [];
  const matches = query.trim() ? all.filter((one) => one.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 6) : [];
  return (
    <div className="source-field">
      <span className="source-label">{label}</span>
      {options === null ? (
        <p className="source-note">Cargando…</p>
      ) : all.length > MANY ? (
        <>
          <TextField label={`Buscar ${ask.label.toLowerCase()}`} type="search" value={query} placeholder={ask.placeholder} onChange={setQuery} />
          {matches.length > 0 && (
            <List>
              {matches.map((one) => (
                <ListRow
                  key={one.code}
                  title={one.name}
                  value={one.code}
                  onClick={() => {
                    onChange({ choice: one });
                    setQuery("");
                  }}
                />
              ))}
            </List>
          )}
        </>
      ) : all.length > 0 || ask.optional ? (
        <ChoiceChips
          label={ask.label}
          options={[...(ask.optional ? [{ value: NONE, label: ask.none_label ?? "Ninguno" }] : []), ...all.map((one) => ({ value: one.code, label: one.name }))]}
          value={chosen?.code ?? NONE}
          onChange={(code) => onChange({ choice: all.find((one) => one.code === code) ?? null })}
        />
      ) : (
        <p className="source-note">No hay nada que elegir.</p>
      )}
      {ask.help && <p className="source-note">{ask.help}</p>}
    </div>
  );
}
