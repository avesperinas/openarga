import { AppSettings, Button, CopyField, Hint, Section, SelectField, Skeleton, TextField, useLocale, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Goal, Unauthorised, readGoals, readSteps, saveGoals, signIn } from "./api";
import { APP } from "./Header";
import { bandLabel, parseKg } from "./weight";

type Way = "none" | "down" | "up";

const WAYS: Way[] = ["none", "down", "up"];

export function parseSteps(text: string): number | null {
  const value = Number(text.trim().replace(/[.,\s]/g, ""));
  return text.trim() !== "" && Number.isInteger(value) && value >= 100 && value <= 100000 ? value : null;
}

export function SettingsScreen() {
  const t = useT();
  const locale = useLocale();
  const asText = (value: number | null) => (value === null ? "" : value.toLocaleString(locale));
  const [goal, setGoal] = useState<Goal | null>(null);
  const [steps, setSteps] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [way, setWay] = useState<Way>("none");
  const [saying, setSaying] = useState("");

  useEffect(() => {
    readGoals()
      .then((found) => {
        setGoal(found);
        setSteps(found.steps_per_day === null ? "" : String(found.steps_per_day));
        setLow(asText(found.weight_min_kg));
        setHigh(asText(found.weight_max_kg));
        setWay(found.weight_direction ?? "none");
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(t("settings.read_failed"));
      });
  }, [locale, t]);

  const wanted: Goal = {
    steps_per_day: parseSteps(steps),
    weight_min_kg: parseKg(low),
    weight_max_kg: parseKg(high),
    weight_direction: way === "none" ? null : way,
  };
  const bad = {
    steps: steps.trim() !== "" && wanted.steps_per_day === null,
    low: low.trim() !== "" && wanted.weight_min_kg === null,
    high: high.trim() !== "" && wanted.weight_max_kg === null,
  };
  const upsideDown =
    wanted.weight_min_kg !== null && wanted.weight_max_kg !== null && wanted.weight_min_kg > wanted.weight_max_kg;
  const valid = !bad.steps && !bad.low && !bad.high && !upsideDown;

  const save = () => {
    if (!valid) return;
    saveGoals(wanted)
      .then((saved) => {
        setGoal(saved);
        setSaying(t("settings.saved"));
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(error instanceof Error ? error.message : t("settings.save_failed"));
      });
  };

  return (
    <AppSettings app={APP}>
      {goal === null && !saying && <Skeleton label={t("settings.loading")} />}
      {goal !== null && (
        <Section title={t("settings.goals")}>
          <div className="surface vitals-card">
            <TextField
              label={t("settings.steps_per_day")}
              value={steps}
              onChange={setSteps}
              inputMode="numeric"
              placeholder="8000"
              invalid={bad.steps}
              hint={bad.steps ? t("settings.steps_bounds") : t("settings.empty_no_goal")}
            />
            <SelectField
              label={t("panel.weight")}
              value={way}
              onChange={setWay}
              options={WAYS.map((value) => ({ value, label: t(`settings.way.${value}`) }))}
            />
            <div className="vitals-log-fields">
              <TextField
                label={t("settings.weight_min")}
                value={low}
                onChange={setLow}
                inputMode="decimal"
                invalid={bad.low || upsideDown}
                hint={bad.low ? t("weight.bounds") : undefined}
              />
              <TextField
                label={t("settings.weight_max")}
                value={high}
                onChange={setHigh}
                inputMode="decimal"
                invalid={bad.high || upsideDown}
                hint={upsideDown ? t("settings.upside_down") : bad.high ? t("weight.bounds") : undefined}
              />
            </div>
            <Hint>{t("settings.band", { band: bandLabel(wanted, t, locale) })}</Hint>
            <Button variant="primary" block disabled={!valid} onClick={save}>
              {t("common.save")}
            </Button>
          </div>
        </Section>
      )}
      {saying && <Hint>{saying}</Hint>}
      <GoogleHealth />
      <AppleHealth />
    </AppSettings>
  );
}

export const SHORTCUT_FIELDS: { key: string; how: "mean" | "sum" | "min" | "max" }[] = [
  { key: "resting_heart_rate", how: "mean" },
  { key: "heart_rate_avg", how: "mean" },
  { key: "heart_rate_min", how: "min" },
  { key: "heart_rate_max", how: "max" },
  { key: "walking_heart_rate", how: "mean" },
  { key: "hrv_ms", how: "mean" },
  { key: "vo2max", how: "mean" },
  { key: "active_kcal", how: "sum" },
  { key: "basal_kcal", how: "sum" },
  { key: "distance_km", how: "sum" },
  { key: "exercise_min", how: "sum" },
  { key: "stand_min", how: "sum" },
  { key: "flights", how: "sum" },
  { key: "walking_speed_kmh", how: "mean" },
  { key: "step_length_cm", how: "mean" },
  { key: "headphone_db", how: "mean" },
  { key: "environment_db", how: "mean" },
];

export const GOOGLE_REDIRECT = `${typeof window === "undefined" ? "" : window.location.origin}/hub/google/callback`;

const GOOGLE_STEPS = ["google.step1", "google.step2", "google.step3", "google.step4"];

const SHORTCUT_STEPS = [
  "shortcut.step1",
  "shortcut.step2",
  "shortcut.step3",
  "shortcut.step4",
  "shortcut.step5",
  "shortcut.step6",
  "shortcut.step7",
  "shortcut.step8",
];

function useLastReceived(): string | null | undefined {
  const [last, setLast] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    readSteps()
      .then((found) => setLast(found.last_received))
      .catch(() => setLast(undefined));
  }, []);
  return last;
}

function GoogleHealth() {
  const t = useT();
  const locale = useLocale();
  const last = useLastReceived();

  return (
    <Section title="Google Health">
      <div className="surface vitals-card">
        <Hint>
          {last
            ? t("steps.last_received", {
                when: new Date(last).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }),
              })
            : t("google.nothing_yet")}
        </Hint>
        <ol className="vitals-steps">
          {GOOGLE_STEPS.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ol>
        <CopyField label={t("google.redirect")} value={GOOGLE_REDIRECT} />
        <Button variant="tinted" onClick={() => window.location.assign("/hub/")}>
          {t("settings.open_hub")}
        </Button>
        <Hint>{t("google.missing")}</Hint>
      </div>
    </Section>
  );
}

export const PUSH_URL = `${typeof window === "undefined" ? "" : window.location.origin}/api/hub/push/apple-health`;

function AppleHealth() {
  const t = useT();
  const locale = useLocale();
  const last = useLastReceived();

  return (
    <Section title={t("apple.title")}>
      <div className="surface vitals-card">
        <Hint>
          {last
            ? t("apple.last_push", {
                when: new Date(last).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" }),
              })
            : t("apple.nothing_yet")}
        </Hint>
        <details className="vitals-fields">
          <summary>{t("shortcut.how")}</summary>
          <ol className="vitals-steps">
            {SHORTCUT_STEPS.map((key) => (
              <li key={key}>{t(key)}</li>
            ))}
          </ol>
          <CopyField label={t("shortcut.url")} value={PUSH_URL} />
        </details>
        <details className="vitals-fields">
          <summary>{t("shortcut.more")}</summary>
          <dl>
            {SHORTCUT_FIELDS.map((one) => (
              <div key={one.key}>
                <dt>
                  <code>{one.key}</code>
                </dt>
                <dd>
                  {t(`shortcut.type.${one.key}`)} · {t(`shortcut.how.${one.how}`)}
                </dd>
              </div>
            ))}
          </dl>
        </details>
        <Button variant="tinted" onClick={() => window.location.assign("/hub/")}>
          {t("settings.open_hub")}
        </Button>
        <Hint>{t("apple.note")}</Hint>
      </div>
    </Section>
  );
}
