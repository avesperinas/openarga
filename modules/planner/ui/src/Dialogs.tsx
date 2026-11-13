import { Button, CheckChips, SegmentedControl, Sheet, TONES, TextField, type Tone, useNow } from "@openarga/ui";
import * as React from "react";

import type { Display, Layer, Scope } from "./api";
import { statusLine } from "./Subscribe";
import { t } from "./lang";

const scopeLabel = (scope: Scope) => t(`scope.${scope}`);

export interface ScopeQuestion {
  question: "edit" | "cancel";
  allowed: Scope[];
  resolve: (scope: Scope | null) => void;
}

export function ScopeDialog({ ask }: { ask: ScopeQuestion }) {
  const close = React.useCallback(() => ask.resolve(null), [ask]);
  return (
    <Sheet title={ask.question === "edit" ? t("scope.edit_title") : t("scope.cancel_title")} onClose={close}>
      <p className="cr-sheet-note">
        {ask.question === "edit" ? t("scope.edit_ask") : t("scope.cancel_note")}
      </p>
      <div className="cr-scope">
        {ask.allowed.map((scope, index) => (
          <Button
            key={scope}
            block
            variant={ask.question === "cancel" ? "destructive" : index === 0 ? "primary" : "secondary"}
            autoFocus={index === 0}
            onClick={() => ask.resolve(scope)}
          >
            {scopeLabel(scope)}
          </Button>
        ))}
        <Button block variant="plain" onClick={close}>
          {ask.question === "edit" ? t("scope.keep") : t("scope.dont_cancel")}
        </Button>
      </div>
    </Sheet>
  );
}

const displays = (): { value: Display; label: string }[] => [
  { value: "events", label: t("display.events") },
  { value: "background", label: t("display.background") },
];

export function LayerSheet({
  layer,
  layers,
  onClose,
  onSave,
}: {
  layer: Layer | null;
  layers: Layer[];
  onClose: () => void;
  onSave: (name: string, tone: Tone, display: Display, daysOffFrom: string[]) => Promise<void>;
}) {
  const [name, setName] = React.useState(layer?.name ?? "");
  const [tone, setTone] = React.useState<Tone>((layer?.tone as Tone) ?? 5);
  const [display, setDisplay] = React.useState<Display>(layer?.display ?? "events");
  const [daysOffFrom, setDaysOffFrom] = React.useState<string[]>(layer?.days_off_from ?? []);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const now = useNow(60_000);
  const subscribed = layer?.origin === "subscription";
  const own = !layer || layer.origin === "own";
  const offSources = layers.filter((one) => one.id !== layer?.id && one.origin !== "app");
  const save = async () => {
    if (!name.trim()) {
      setError(t("form.no_name"));
      return;
    }
    setBusy(true);
    try {
      await onSave(name.trim(), tone, display, daysOffFrom.filter((id) => offSources.some((one) => one.id === id)));
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      title={subscribed ? t("layer.subscription") : layer?.origin === "app" ? t("layer.from_app") : layer ? t("layer.layer") : t("layer.new")}
      onClose={onClose}
      action={{ label: busy ? t("action.saving") : layer ? t("action.save") : t("layer.create"), onClick: () => void save(), disabled: busy }}
    >
      <TextField label={t("field.name")} value={name} placeholder={t("layer.placeholder")} autoFocus onChange={setName} onSubmit={() => void save()} invalid={!!error} hint={error ?? undefined} />
      <div className="cr-tones" role="radiogroup" aria-label={t("field.tone")}>
        {TONES.map((one) => (
          <button
            key={one.tone}
            type="button"
            role="radio"
            aria-checked={tone === one.tone}
            aria-label={one.name}
            title={one.name}
            className="cr-tone"
            data-tone={one.tone}
            onClick={() => setTone(one.tone)}
          />
        ))}
      </div>
      <div className="cr-display">
        <span className="cr-display-label">{t("display.label")}</span>
        <SegmentedControl label={t("display.label")} options={displays()} value={display} onChange={setDisplay} />
        <p className="cr-sheet-note">
          {display === "background"
            ? t("display.background_hint")
            : t("display.events_hint")}
        </p>
      </div>
      {own && offSources.length > 0 && (
        <div className="cr-display">
          <span className="cr-display-label">{t("daysoff.label")}</span>
          <CheckChips
            label={t("daysoff.label")}
            options={offSources.map((one) => ({ value: one.id, label: one.name }))}
            values={daysOffFrom}
            onChange={setDaysOffFrom}
          />
          <p className="cr-sheet-note">
            {t("daysoff.hint")}
          </p>
        </div>
      )}
      {layer?.origin === "app" && (
        <p className="cr-sheet-note">{t("layer.app_note")}</p>
      )}
      {subscribed && layer && (
        <div className="cr-subscription-foot">
          <p className="cr-sheet-note" data-failing={layer.subscription?.failing || undefined}>
            {statusLine(layer, now)}. {t("layer.sub_note")}
          </p>
          {layer.connection_id && (
            <a className="cr-link" href={`/hub/${layer.connection_id}`}>
              {t("layer.hub_link")}
            </a>
          )}
        </div>
      )}
    </Sheet>
  );
}
