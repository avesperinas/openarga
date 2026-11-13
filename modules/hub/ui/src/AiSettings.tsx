import { usePreferences } from "@openarga/app";
import {
  Button,
  Card,
  Hint,
  List,
  ListRow,
  SelectField,
  TextField,
  type Translate,
  createT,
  numbers,
} from "@openarga/ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type AiChoice,
  type AiProvider,
  type AiSettings as Settings,
  type AiSpending,
  forgetAiKey,
  readAiSettings,
  readAiSpending,
  saveAiKey,
  saveAiSettings,
} from "./ai";
import en from "./i18n/en.json";
import es from "./i18n/es.json";

const CATALOGS = { en, es };
const DEFAULTS: Partial<Record<AiProvider, { fast: string; smart: string }>> = {
  anthropic: { fast: "claude-haiku-5-5", smart: "claude-opus-5-5" },
};

const count = (value: number) => numbers({ maximumFractionDigits: 0 }).format(value);

export function choiceOf(settings: Settings): AiChoice {
  return {
    provider: settings.provider,
    base_url: settings.mine.base_url,
    fast_model: settings.mine.fast_model,
    smart_model: settings.mine.smart_model,
    monthly_tokens: settings.mine.monthly_tokens,
  };
}

export function spentLine(t: Translate, spending: AiSpending): string {
  return spending.monthly_tokens === null
    ? t("ai.spent", { spent: count(spending.spent) })
    : t("ai.spent.of", { spent: count(spending.spent), budget: count(spending.monthly_tokens) });
}

const blank = (value: string) => (value.trim() ? value.trim() : null);

export function AiForm({
  t,
  settings,
  onSave,
  onKey,
  onForget,
}: {
  t: Translate;
  settings: Settings;
  onSave: (choice: AiChoice) => Promise<void>;
  onKey: (key: string) => Promise<void>;
  onForget: () => Promise<void>;
}) {
  const [choice, setChoice] = useState(() => choiceOf(settings));
  const [key, setKey] = useState("");
  const [said, setSaid] = useState("");
  const provider = choice.provider ?? "none";
  const defaults = DEFAULTS[provider];
  const options: AiProvider[] = ["none", "anthropic", "openai", ...(settings.provider === "fake" ? ["fake" as const] : [])];

  const run = async (work: () => Promise<void>) => {
    try {
      await work();
      setSaid(t("ai.saved"));
    } catch (error) {
      setSaid(t("ai.failed", { reason: error instanceof Error ? error.message : String(error) }));
    }
  };
  const set = (change: Partial<AiChoice>) => {
    setSaid("");
    setChoice((current) => ({ ...current, ...change }));
  };

  return (
    <>
      <Hint>{t("ai.intro")}</Hint>
      <SelectField
        label={t("ai.provider")}
        options={options.map((value) => ({ value, label: t(`ai.provider.${value}`) }))}
        value={provider}
        onChange={(value) => set({ provider: value })}
      />
      {provider === "none" && <Hint>{t("ai.provider.none.hint")}</Hint>}
      {provider === "openai" && <Hint>{t("ai.provider.openai.hint")}</Hint>}
      {(provider === "anthropic" || provider === "openai") && (
        <>
          <TextField
            label={t("ai.base_url")}
            value={choice.base_url ?? ""}
            hint={t(`ai.base_url.hint.${provider}`)}
            invalid={provider === "openai" && !choice.base_url}
            onChange={(value) => set({ base_url: blank(value) })}
          />
          <TextField
            label={t("ai.fast_model")}
            value={choice.fast_model ?? ""}
            placeholder={defaults?.fast}
            hint={defaults ? t("ai.model.default", { model: defaults.fast }) : undefined}
            onChange={(value) => set({ fast_model: blank(value) })}
          />
          <TextField
            label={t("ai.smart_model")}
            value={choice.smart_model ?? ""}
            placeholder={defaults?.smart}
            hint={defaults ? t("ai.model.default", { model: defaults.smart }) : undefined}
            onChange={(value) => set({ smart_model: blank(value) })}
          />
          <TextField
            label={t("ai.monthly_tokens")}
            value={choice.monthly_tokens === null ? "" : String(choice.monthly_tokens)}
            inputMode="numeric"
            hint={t("ai.monthly_tokens.hint")}
            onChange={(value) => {
              const digits = value.replace(/\D/g, "");
              set({ monthly_tokens: digits ? Number(digits) : null });
            }}
          />
        </>
      )}
      <Button variant="primary" onClick={() => void run(() => onSave(choice))}>
        {t("ai.save")}
      </Button>
      {(provider === "anthropic" || provider === "openai") && (
        <>
          <TextField label={t("ai.key")} type="password" value={key} onChange={setKey} />
          <Hint>
            {settings.own_key && settings.key_hint
              ? t("ai.key.mine", { hint: settings.key_hint })
              : settings.instance_key
                ? t("ai.key.instance")
                : t("ai.key.none")}
          </Hint>
          <Button
            disabled={key.trim().length < 8}
            onClick={() =>
              void run(async () => {
                await onKey(key.trim());
                setKey("");
              })
            }
          >
            {t("ai.key.save")}
          </Button>
          {settings.own_key && <Button onClick={() => void run(onForget)}>{t("ai.key.forget")}</Button>}
        </>
      )}
      {said && <Hint announce>{said}</Hint>}
    </>
  );
}

export function AiAttempts({ t, spending }: { t: Translate; spending: AiSpending }) {
  return (
    <>
      <Hint>{spentLine(t, spending)}</Hint>
      {spending.attempts.length === 0 ? (
        <Hint>{t("ai.attempts.empty")}</Hint>
      ) : (
        <List>
          {spending.attempts.slice(0, 10).map((attempt) => (
            <ListRow
              key={attempt.id}
              title={t("ai.attempt.line", {
                app: attempt.app,
                capability: attempt.capability,
                model: attempt.model,
                tokens: count(attempt.input_tokens + attempt.output_tokens),
              })}
              subtitle={[t(`ai.status.${attempt.status}`), attempt.detail].filter(Boolean).join(" · ")}
            />
          ))}
        </List>
      )}
    </>
  );
}

export function AiSettings() {
  const { locale } = usePreferences();
  const t = useMemo(() => createT(CATALOGS, locale), [locale]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [spending, setSpending] = useState<AiSpending | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    readAiSettings()
      .then(setSettings)
      .catch(() => setFailed(true));
    readAiSpending()
      .then(setSpending)
      .catch(() => setSpending(null));
  }, []);
  useEffect(load, [load]);

  return (
    <Card title={t("ai.title")}>
      {failed && <Hint tone="warning">{t("ai.unavailable")}</Hint>}
      {settings && (
        <AiForm
          t={t}
          settings={settings}
          onSave={async (choice) => setSettings(await saveAiSettings(choice))}
          onKey={async (key) => {
            await saveAiKey(key);
            load();
          }}
          onForget={async () => {
            await forgetAiKey();
            load();
          }}
        />
      )}
      {spending && (
        <>
          <h3 className="visually-hidden">{t("ai.attempts")}</h3>
          <AiAttempts t={t} spending={spending} />
        </>
      )}
    </Card>
  );
}
