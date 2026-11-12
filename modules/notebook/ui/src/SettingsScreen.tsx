import { mutate } from "@openarga/app";
import { AppSettings, Button, Hint, Notice, OfflineNotice, Section, SelectField, TextField, useToast } from "@openarga/ui";
import * as React from "react";

import { type Settings, pushExport, readExport, readPropertyNames, readSettings, writeSettings } from "./api";
import { APP } from "./identity";
import { Pending, useLoad } from "./Loads";
import { ago } from "./when";

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
          toast({ message: "Guardado" });
        } catch (error) {
          toast({ message: (error as Error).message, tone: "error" });
        }
      }}
    >
      <Section title="Nota del día">
        <TextField
          label="Carpeta"
          value={settings.daily_folder}
          onChange={(daily_folder) => setDraft({ ...settings, daily_folder })}
          hint="Cada día tiene su nota, que se llama como el día: 2026-09-28."
        />
      </Section>
      <Section title="Repaso">
        <SelectField
          label="Propiedad con la fecha del próximo repaso"
          value={settings.review_property ?? ""}
          onChange={(value) => setDraft({ ...settings, review_property: value || null })}
          options={[
            { value: "", label: "Ninguna" },
            ...dates.map((n) => ({ value: n.name, label: `${n.name} · ${n.notes} ${n.notes === 1 ? "nota" : "notas"}` })),
          ]}
        />
        <Hint>
          {dates.length === 0
            ? "Ninguna propiedad de tus notas es una fecha todavía."
            : "Las notas con esa fecha hoy o antes salen en «Repasar» y en su widget."}
        </Hint>
      </Section>
      <Button type="submit" variant="primary" disabled={draft === null}>
        Guardar
      </Button>
    </form>
  );
}

function CopySection() {
  const toast = useToast();
  const { data: state, found } = useLoad("export", readExport);
  const [busy, setBusy] = React.useState(false);
  return (
    <Section title="Copia en GitHub">
      {!state ? (
        <Pending found={found} rows={2} />
      ) : state.outcome === "unconnected" || state.outcome === null ? (
        <Hint>
          Tus notas se copian solas en un repo privado tuyo, como ficheros .md que se abren en Obsidian. Conéctalo en{" "}
          <a href="/hub" className="mn-inline-link">
            Hub
          </a>
          , en Notas → GitHub, con un token de ese repo que pueda escribir su contenido.
        </Hint>
      ) : state.outcome === "ok" ? (
        <Notice tone="positive" title={`Copiado ${state.pushed_at ? ago(state.pushed_at) : ""}`}>
          {state.pending > 0
            ? `${state.pending} ${state.pending === 1 ? "cambio espera" : "cambios esperan"} a la siguiente copia, como mucho en diez minutos. `
            : "Todo está en el repo. "}
          {state.commit_url && (
            <a href={state.commit_url} target="_blank" rel="noopener noreferrer" className="mn-inline-link">
              Ver el último commit
            </a>
          )}
        </Notice>
      ) : (
        <Notice tone="warning" title="La última copia no se ha podido hacer">
          {state.detail}
          {state.pushed_at && ` La última buena fue ${ago(state.pushed_at)}.`}
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
          Copiar ahora
        </Button>
      )}
    </Section>
  );
}
