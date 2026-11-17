"use client";

import { Button, Hint, Notice, Screen, Section, ToggleList, ToggleRow, createT } from "@openarga/ui";
import * as React from "react";

import en from "../i18n/en.json";
import es from "../i18n/es.json";
import { type PersonPreferences, changePersonPreferences } from "../lib/regional";
import { request } from "../lib/session";
import { RegionForm } from "./RegionSettings";

const CATALOGS = { en, es };
const UI_PREFERENCES = "/api/kernel/ui/preferences";

export interface WelcomeApp {
  id: string;
  name: string;
  hue?: number | null;
}

export async function finishFirstRun(region: PersonPreferences, hidden: string[]): Promise<void> {
  await changePersonPreferences(region);
  const current = await request(UI_PREFERENCES, { headers: { accept: "application/json" } });
  if (!current.ok) throw new Error(String(current.status));
  const saved = await request(UI_PREFERENCES, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ...(await current.json()), hidden_apps: hidden }),
  });
  if (!saved.ok) throw new Error(String(saved.status));
}

export function Welcome({
  initial,
  apps,
  finish = finishFirstRun,
  done = () => window.location.assign("/"),
}: {
  initial: PersonPreferences;
  apps: WelcomeApp[];
  finish?: (region: PersonPreferences, hidden: string[]) => Promise<void>;
  done?: () => void;
}) {
  const [region, setRegion] = React.useState(initial);
  const [step, setStep] = React.useState<"region" | "apps">("region");
  const [hidden, setHidden] = React.useState<Set<string>>(new Set());
  const [status, setStatus] = React.useState<"idle" | "saving" | "failed">("idle");
  const t = React.useMemo(() => createT(CATALOGS, region.locale), [region.locale]);

  const toggle = (id: string, shown: boolean) =>
    setHidden((current) => {
      const next = new Set(current);
      if (shown) next.delete(id);
      else next.add(id);
      return next;
    });

  const complete = async () => {
    setStatus("saving");
    try {
      await finish(region, apps.map((app) => app.id).filter((id) => hidden.has(id)));
      done();
    } catch {
      setStatus("failed");
    }
  };

  return (
    <Screen label={t("welcome.title")}>
      <Section title={t("welcome.title")}>
        <Hint>{t(step === "region" ? "welcome.region.intro" : "welcome.apps.intro")}</Hint>
      </Section>
      {step === "region" ? (
        <RegionForm
          initial={region}
          action={t("welcome.next")}
          onSave={async (next) => {
            setRegion(next);
            setStep("apps");
          }}
        />
      ) : (
        <Section title={t("welcome.apps.title")}>
          <ToggleList label={t("welcome.apps.title")}>
            {apps.map((app) => (
              <ToggleRow
                key={app.id}
                name={app.name}
                tone={app.hue ?? undefined}
                checked={!hidden.has(app.id)}
                onChange={(shown) => toggle(app.id, shown)}
              />
            ))}
          </ToggleList>
          <Hint>{t("welcome.apps.later")}</Hint>
          <div className="settings-actions">
            <Button onClick={() => setStep("region")} disabled={status === "saving"}>
              {t("welcome.back")}
            </Button>
            <Button variant="primary" onClick={() => void complete()} disabled={status === "saving"}>
              {status === "saving" ? t("welcome.saving") : t("welcome.finish")}
            </Button>
          </div>
          {status === "failed" && <Notice tone="negative">{t("welcome.failed")}</Notice>}
        </Section>
      )}
    </Screen>
  );
}
