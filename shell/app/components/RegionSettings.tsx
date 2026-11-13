"use client";

import {
  Button,
  Hint,
  LOCALES,
  type Locale,
  Notice,
  Section,
  SegmentedControl,
  SelectField,
  TextField,
  createT,
  intlLocale,
} from "@openarga/ui";
import * as React from "react";

import en from "../i18n/en.json";
import es from "../i18n/es.json";
import {
  AREA,
  type PersonPreferences,
  REGION,
  changePersonPreferences,
  countries,
  currencies,
  readPersonPreferences,
  timeZones,
} from "../lib/regional";

const CATALOGS = { en, es };

const SAMPLE_AMOUNT = 1234.5;

export function nativeName(locale: Locale): string {
  const name = new Intl.DisplayNames([locale], { type: "language" }).of(locale) ?? locale;
  return name.charAt(0).toLocaleUpperCase(locale) + name.slice(1);
}

export function sampleOf(preferences: PersonPreferences, now = new Date()): string {
  const tag = intlLocale(preferences.locale, preferences.country);
  const when = new Intl.DateTimeFormat(tag, { dateStyle: "full", timeStyle: "short", timeZone: preferences.timezone }).format(now);
  const amount = new Intl.NumberFormat(tag, { style: "currency", currency: preferences.currency }).format(SAMPLE_AMOUNT);
  return `${when} · ${amount}`;
}

export function problemsOf(preferences: PersonPreferences): { region?: true; area?: true } {
  const problems: { region?: true; area?: true } = {};
  if (preferences.region && (!REGION.test(preferences.region) || (preferences.country && !preferences.region.startsWith(`${preferences.country}-`))))
    problems.region = true;
  if (preferences.area && !AREA.test(preferences.area)) problems.area = true;
  return problems;
}

type Status = "idle" | "saving" | "saved" | "failed";

export function RegionForm({
  initial,
  onSave,
}: {
  initial: PersonPreferences;
  onSave: (next: PersonPreferences) => Promise<void>;
}) {
  const [draft, setDraft] = React.useState(initial);
  const [status, setStatus] = React.useState<Status>("idle");
  const t = React.useMemo(() => createT(CATALOGS, draft.locale), [draft.locale]);
  const set = (change: Partial<PersonPreferences>) => {
    setStatus("idle");
    setDraft((current) => ({ ...current, ...change }));
  };
  const problems = problemsOf(draft);
  const example = "ES-NA";
  const countryList = React.useMemo(() => countries(draft.locale), [draft.locale]);

  const save = async () => {
    setStatus("saving");
    try {
      await onSave(draft);
      setStatus("saved");
    } catch {
      setStatus("failed");
    }
  };

  return (
    <Section title={t("region.title")}>
      <SegmentedControl
        label={t("region.language")}
        options={LOCALES.map((one) => ({ value: one, label: nativeName(one) }))}
        value={draft.locale}
        onChange={(locale) => set({ locale })}
      />
      <div className="settings-fields">
        <SelectField
          label={t("region.timezone")}
          options={timeZones(draft.timezone).map((zone) => ({ value: zone, label: zone.replaceAll("_", " ") }))}
          value={draft.timezone}
          onChange={(timezone) => set({ timezone })}
        />
        <SelectField
          label={t("region.currency")}
          options={currencies(draft.currency).map((code) => ({ value: code, label: code }))}
          value={draft.currency}
          onChange={(currency) => set({ currency })}
        />
        <SelectField
          label={t("region.country")}
          options={[{ value: "", label: t("region.country.none") }, ...countryList.map((one) => ({ value: one.code, label: one.name }))]}
          value={draft.country ?? ""}
          onChange={(country) =>
            set({
              country: country || null,
              region: country && draft.region?.startsWith(`${country}-`) ? draft.region : null,
            })
          }
        />
        <TextField
          label={t("region.region")}
          value={draft.region ?? ""}
          placeholder={example}
          onChange={(value) => set({ region: value.trim().toUpperCase() || null })}
        />
        <Hint>{problems.region ? t("region.invalid.region", { example }) : t("region.region.hint", { example })}</Hint>
        <TextField
          label={t("region.area")}
          value={draft.area ?? ""}
          onChange={(value) => set({ area: value.trim().toLowerCase() || null })}
        />
        <Hint>{problems.area ? t("region.invalid.area") : t("region.area.hint")}</Hint>
      </div>
      <Hint>{t("region.preview", { sample: sampleOf(draft) })}</Hint>
      <Button onClick={() => void save()} disabled={status === "saving" || Object.keys(problems).length > 0}>
        {status === "saving" ? t("region.saving") : t("region.save")}
      </Button>
      {status === "saved" && <Notice tone="positive">{t("region.saved")}</Notice>}
      {status === "failed" && <Notice tone="negative">{t("region.failed")}</Notice>}
    </Section>
  );
}

export function RegionSettings({ locale }: { locale: Locale }) {
  const [found, setFound] = React.useState<PersonPreferences | null>(null);
  const [failed, setFailed] = React.useState(false);
  const t = React.useMemo(() => createT(CATALOGS, locale), [locale]);

  React.useEffect(() => {
    readPersonPreferences()
      .then(setFound)
      .catch(() => setFailed(true));
  }, []);

  if (failed)
    return (
      <Section title={t("region.title")}>
        <Hint>{t("region.unavailable")}</Hint>
      </Section>
    );
  if (!found)
    return (
      <Section title={t("region.title")}>
        <Hint>{t("region.loading")}</Hint>
      </Section>
    );
  return (
    <RegionForm
      initial={found}
      onSave={async (next) => {
        await changePersonPreferences(next);
        window.setTimeout(() => window.location.reload(), 800);
      }}
    />
  );
}
