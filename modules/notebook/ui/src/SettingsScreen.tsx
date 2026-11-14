import { mutate } from "@openarga/app";
import { AppSettings, Button, Hint, Notice, OfflineNotice, Section, SelectField, TextField, useToast } from "@openarga/ui";
import * as React from "react";

import { type Settings, pushExport, readExport, readPropertyNames, readSettings, writeSettings } from "./api";
import { APP } from "./identity";
import { Pending, useLoad } from "./Loads";
import { ago } from "./when";
import { t } from "./lang";

export function SettingsScreen() {
  return (
    <AppSettings app={APP}>
      <OfflineNotice />
      <OwnSettings />
      <CopySection />
    </AppSettings>
  );
}

function OwnSettings() {
  const toast = useToast();
  const { data: saved, found } = useLoad("settings", readSettings, { persist: true });
  const names = useLoad("properties", readPropertyNames).data ?? [];
  const [draft, setDraft] = React.useState<Settings | null>(null);
  const settings = draft ?? saved;

  if (!settings) return <Pending found={found} rows={4} />;
  const dates = names.filter((n) => n.dates);

  return (
    <form
      className="mn-settings"
      onSubmit={async (event) => {
        event.preventDefault();
        try {
          await mutate<Settings>("settings", settings, { request: () => writeSettings(settings) });
          setDraft(null);
          toast({ message: t("editor.saved") });
        } catch (error) {
          toast({ message: (error as Error).message, tone: "error" });
        }
      }}
    >
      <Section title={t("settings.daily")}>
        <TextField
          label={t("move.folder")}
          value={settings.daily_folder}
          onChange={(daily_folder) => setDraft({ ...settings, daily_folder })}
          hint={t("settings.daily_hint")}
        />
      </Section>
      <Section title={t("settings.review")}>
        <SelectField
          label={t("settings.review_property")}
          value={settings.review_property ?? ""}
          onChange={(value) => setDraft({ ...settings, review_property: value || null })}
          options={[
            { value: "", label: t("settings.none") },
            ...dates.map((n) => ({ value: n.name, label: `${n.name} · ${t(n.notes === 1 ? "count.notes.one" : "count.notes.other", { count: n.notes })}` })),
          ]}
        />
        <Hint>
          {dates.length === 0
            ? t("settings.no_dates")
            : t("settings.review_hint")}
        </Hint>
      </Section>
      <Button type="submit" variant="primary" disabled={draft === null}>
        {t("action.save")}
      </Button>
    </form>
  );
}

function CopySection() {
  const toast = useToast();
  const { data: state, found } = useLoad("export", readExport);
  const [busy, setBusy] = React.useState(false);
  return (
    <Section title={t("copy.title")}>
      {!state ? (
        <Pending found={found} rows={2} />
      ) : state.outcome === "unconnected" || state.outcome === null ? (
        <Hint>
          {t("copy.how_before")}{" "}
          <a href="/hub" className="mn-inline-link">
            Hub
          </a>
          {t("copy.how_after")}
        </Hint>
      ) : state.outcome === "ok" ? (
        <Notice tone="positive" title={t("copy.done", { when: state.pushed_at ? ago(state.pushed_at) : "" }).trim()}>
          {state.pending > 0
            ? `${t(state.pending === 1 ? "copy.pending.one" : "copy.pending.other", { count: state.pending })} `
            : `${t("copy.all_there")} `}
          {state.commit_url && (
            <a href={state.commit_url} target="_blank" rel="noopener noreferrer" className="mn-inline-link">
              {t("copy.last_commit")}
            </a>
          )}
        </Notice>
      ) : (
        <Notice tone="warning" title={t("copy.failed")}>
          {state.detail}
          {state.pushed_at && ` ${t("copy.last_good", { when: ago(state.pushed_at) })}`}
        </Notice>
      )}
      {state && (
        <Button
          variant="secondary"
          icon="repeat"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await mutate("export", undefined, { request: pushExport });
            } catch (error) {
              toast({ message: (error as Error).message, tone: "error" });
            } finally {
              setBusy(false);
            }
          }}
        >
          {t("copy.now")}
        </Button>
      )}
    </Section>
  );
}
