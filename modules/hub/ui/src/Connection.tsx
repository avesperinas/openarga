import {
  Button,
  Card,
  ConfirmDelete,
  CredentialField,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  Sheet,
  TextField,
} from "@openarga/ui";
import { useCallback, useState } from "react";

import {
  type ConnectionDetail,
  type Run,
  type SecretStatus,
  Refused,
  Unauthorised,
  changeCredential,
  pauseConnection,
  reauthorize,
  readConnection,
  removeConnection,
  renameConnection,
  renewToken,
  resumeConnection,
  signIn,
  syncNow,
} from "./api";
import { TokenSheet } from "./Add";
import { ClaudeRun } from "./ClaudeRun";
import { ScreenHeader } from "./Header";
import { Pending, changed, useLoad } from "./Loads";
import { MailRules } from "./Rules";

const MOMENT = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function when(iso: string): string {
  return MOMENT.format(new Date(iso));
}

export function runLine(run: Run): string {
  switch (run.outcome) {
    case "ok":
      if (run.operation === "search") return "Contestó";
      if (run.operation === "run") return run.detail ?? "Hecha";
      return run.emitted === 0 ? "Bien, sin nada nuevo" : `Bien, ${run.emitted} dato${run.emitted === 1 ? "" : "s"} nuevo${run.emitted === 1 ? "" : "s"}`;
    case "error":
      return run.detail ? `Falló: ${run.detail}` : "Falló";
    case "rate_limited":
      return "La fuente pidió esperar";
    case "skipped":
      return run.detail ? `Saltada: ${run.detail}` : "Saltada";
    case "running":
      return "En marcha";
  }
}

const DAY = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", year: "numeric" });

export function budgetLine(budget: NonNullable<ConnectionDetail["budget"]>): string {
  if (budget.remaining === 0) return `Hoy ya no quedan accesos: los ${budget.limit} del día están gastados.`;
  return `Quedan ${budget.remaining} de ${budget.limit} accesos hoy.`;
}

export function mailLine(extractors: { entity: string }[]): string {
  if (extractors.length === 0) {
    return "Todavía no lee ninguna entidad: añade abajo una regla por cada correo que quieras leer.";
  }
  return `Lee los correos de ${extractors.map((extractor) => extractor.entity).join(", ")}. Los demás no se abren.`;
}

const SESSIONS: Record<string, string> = {
  race: "la carrera",
  qualifying: "la clasificación",
  sprint: "el sprint",
  sprint_qualifying: "la clasificación del sprint",
  practice: "los libres",
};

export function calendarLine(connection: Pick<ConnectionDetail, "provider" | "settings">): string | null {
  const settings = connection.settings ?? {};
  if (connection.provider === "holidays") {
    const region = settings.region ? ` y los de ${String(settings.region)}` : "";
    return `Los festivos nacionales de ${String(settings.country ?? "")}${region}.`;
  }
  if (connection.provider === "formula1") {
    const chosen = Array.isArray(settings.sessions) ? settings.sessions : [];
    const names = chosen.map((key) => SESSIONS[key] ?? key);
    const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}` : (names[0] ?? "");
    return `Cada Gran Premio con ${list}.`;
  }
  if (connection.provider === "football") {
    const team = settings.team_name ? String(settings.team_name) : "del equipo";
    return `Los partidos ${settings.team_name ? "de " : ""}${team}: liga, copa y Europa, cada seis horas.`;
  }
  if (connection.provider === "ical" && typeof settings.url === "string") {
    try {
      return `El calendario de ${new URL(settings.url).host}, cada día.`;
    } catch {
      return null;
    }
  }
  if (connection.provider === "ical_private") return "Su dirección se guarda cifrada.";
  return null;
}

export function landsIn(connection: Pick<ConnectionDetail, "inlets">): string | null {
  const apps = [...new Set((connection.inlets ?? []).map((inlet) => inlet.app))];
  if (apps.length === 0) return null;
  const list = apps.length > 1 ? `${apps.slice(0, -1).join(", ")} y ${apps[apps.length - 1]}` : apps[0];
  return `Llega a ${list}.`;
}

export function removeConsequence(connection: ConnectionDetail): string {
  if (connection.provider === "claude") {
    return "Chuping deja de lanzar sus pings y su token se borra. Los pings que ya se lanzaron no se borran.";
  }
  return `Deja de entrar lo que trae ${connection.provider_name}, y su clave se borra. Lo que ya trajo se queda en tus apps.`;
}

export function labelHint(connection: ConnectionDetail): string {
  if (connection.provider === "claude") return "Es como la nombras al pedirle a Claude que cambie su horario.";
  return "Como la verás aquí y en tus apps.";
}

export function ConnectionScreen({ id, onBack }: { id: string; onBack: () => void }) {
  const { data: connection, set, found } = useLoad(`connection:${id}`, () => readConnection(id));
  const [problem, setProblem] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [said, setSaid] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("banco") === "conectado") return "Banco conectado. Trae hasta un año de movimientos: en un minuto empiezan a entrar.";
    if (params.get("google") === "conectado") return "Google Health conectado. Trae los últimos treinta días: en un minuto empiezan a entrar.";
    return null;
  });

  const failed = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Refused ? error.message : "No se ha podido guardar.");
  }, []);

  const show = (next: ConnectionDetail) => {
    setProblem(null);
    set(next);
  };

  if (!connection) {
    return (
      <Screen>
        <ScreenHeader back={{ label: "Estado", onClick: onBack }} title="Conexión" />
        <OfflineNotice />
        <Pending found={found} />
      </Screen>
    );
  }

  return (
    <Screen>
      <ScreenHeader
        back={{ label: "Estado", onClick: onBack }}
        eyebrow={connection.provider_name}
        title={connection.label}
      />
      <OfflineNotice />

      <Card title={connection.brief}>
        {connection.reason && (
          <Hint announce>
            {connection.reason}
          </Hint>
        )}
        <Hint>
          {connection.last_ok_at ? `Última pasada buena: ${when(connection.last_ok_at)}.` : "Todavía no ha traído nada."}
          {connection.emitted_week > 0 && ` ${connection.emitted_week} datos nuevos esta semana.`}
        </Hint>
      </Card>

      {said && (
        <Hint announce>
          {said}
        </Hint>
      )}

      {(connection.authorizes || connection.budget) && (
        <Card title="Acceso">
          {connection.consent_expires_at && connection.state !== "expired" && (
            <Hint>El permiso vale hasta el {DAY.format(new Date(connection.consent_expires_at))}.</Hint>
          )}
          {connection.budget && <Hint>{budgetLine(connection.budget)}</Hint>}
          <div className="hub-actions">
            {connection.budget && (
              <Button
                variant="tinted"
                disabled={syncing || connection.budget.remaining === 0 || connection.paused}
                onClick={() => {
                  setSyncing(true);
                  syncNow(connection.id)
                    .then((updated) => {
                      show(updated);
                      setSaid(updated.outcome === "ok" ? "Sincronizado." : `No ha ido bien: ${updated.outcome_detail ?? updated.outcome}`);
                    })
                    .catch(failed)
                    .finally(() => setSyncing(false));
                }}
              >
                {syncing ? "Sincronizando…" : "Sincronizar ahora"}
              </Button>
            )}
            {connection.authorizes && (
              <Button
                variant={connection.state === "expired" || connection.state === "expiring" ? "primary" : "plain"}
                onClick={() =>
                  reauthorize(connection.id)
                    .then((url) => window.location.assign(url))
                    .catch(failed)
                }
              >
                Reconectar
              </Button>
            )}
          </div>
          {connection.accounts && connection.accounts.length > 0 && (
            <List>
              {connection.accounts.map((account, index) => (
                <ListRow
                  key={`${account.name}-${index}`}
                  title={account.name ?? "Cuenta"}
                  detail={account.iban_tail ? `…${account.iban_tail}` : undefined}
                />
              ))}
            </List>
          )}
        </Card>
      )}

      {connection.extractors && connection.provider === "imap" && (
        <Card title="Buzón">
          {connection.settings && (
            <Hint>
              {String(connection.settings.username ?? "")} en {String(connection.settings.host ?? "")}, carpeta{" "}
              {String(connection.settings.folder ?? "INBOX")}. Solo lectura.
            </Hint>
          )}
          <Hint>
            {mailLine([
              ...new Map(
                [...(connection.rules ?? []), ...connection.extractors].map((one) => [one.entity, one]),
              ).values(),
            ])}
          </Hint>
        </Card>
      )}
      {(calendarLine(connection) || landsIn(connection)) && (
        <Card title="Qué trae">
          {calendarLine(connection) && <Hint>{calendarLine(connection)}</Hint>}
          {landsIn(connection) && <Hint>{landsIn(connection)}</Hint>}
        </Card>
      )}
      {connection.provider === "imap" && <MailRules connection={connection} onChange={show} />}
      {connection.provider === "claude" && (
        <ClaudeRun connection={connection.id} relay={connection.relay !== false} onChange={show} />
      )}

      <Card title="Pasadas">
        {connection.runs.length === 0 ? (
          <Hint>
            {connection.paused
              ? "En pausa: no se llamará a la fuente hasta que la reanudes."
              : "Todavía ninguna. La primera llega en un minuto."}
          </Hint>
        ) : (
          <List>
            {connection.runs.map((run) => (
              <ListRow key={run.started_at} title={when(run.started_at)} detail={runLine(run)} />
            ))}
          </List>
        )}
      </Card>

      {connection.push && (
        <Card title="Token de ingesta">
          <Hint>
            La fuente llama a arga con él. Solo se enseña al generarlo; generar otro retira el anterior.
          </Hint>
          <Button variant="tinted" onClick={() => renewToken(connection.id).then((renewed) => setToken(renewed.ingest_token)).catch(failed)}>
            Generar otro token
          </Button>
        </Card>
      )}
      {token && <TokenSheet token={token} onDone={() => setToken(null)} />}

      {connection.secrets.length > 0 && <Card title="Credenciales">
        {connection.secrets.map((secret) => (
          <Credential
            key={secret.key}
            connectionId={connection.id}
            secret={secret}
            onSaved={show}
            onFailed={failed}
          />
        ))}
      </Card>}

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}

      <div className="hub-actions">
        <Button onClick={onBack}>Volver</Button>
        <Button
          variant="tinted"
          onClick={() =>
            (connection.paused ? resumeConnection : pauseConnection)(connection.id).then(show).catch(failed)
          }
        >
          {connection.paused ? "Reanudar" : "Pausar"}
        </Button>
        <Button variant="plain" icon="edit" onClick={() => setRenaming(true)}>
          Cambiar nombre
        </Button>
        <Button variant="destructive" icon="trash" onClick={() => setRemoving(true)}>
          Quitar
        </Button>
      </div>
      {renaming && (
        <RenameSheet
          connection={connection}
          onClose={() => setRenaming(false)}
          onSaved={(updated) => {
            show(updated);
            setRenaming(false);
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title="¿Quitar esta conexión?"
          subject={connection.label}
          consequence={removeConsequence(connection)}
          action="Quitar conexión"
          onCancel={() => setRemoving(false)}
          onConfirm={() =>
            removeConnection(connection.id).then(() => {
              changed();
              onBack();
            })
          }
        />
      )}
    </Screen>
  );
}

export function RenameSheet({
  connection,
  onClose,
  onSaved,
}: {
  connection: ConnectionDetail;
  onClose: () => void;
  onSaved: (connection: ConnectionDetail) => void;
}) {
  const [label, setLabel] = useState(connection.label);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const save = () => {
    setBusy(true);
    setProblem(null);
    renameConnection(connection.id, label)
      .then(onSaved)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Refused ? error.message : "No se ha podido guardar.");
      })
      .finally(() => setBusy(false));
  };

  return (
    <Sheet title="Cambiar nombre" onClose={onClose} action={{ label: "Guardar", onClick: save, disabled: busy || !label.trim() }}>
      <TextField
        label="Nombre"
        value={label}
        onChange={setLabel}
        onSubmit={save}
        autoFocus
        hint={problem ?? labelHint(connection)}
        invalid={problem !== null}
      />
    </Sheet>
  );
}

function Credential({
  connectionId,
  secret,
  onSaved,
  onFailed,
}: {
  connectionId: string;
  secret: SecretStatus;
  onSaved: (connection: ConnectionDetail) => void;
  onFailed: (error: unknown) => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <CredentialField
      label={secret.label}
      help={secret.help}
      configured={secret.configured}
      hint={secret.hint}
      value={value}
      onChange={setValue}
      busy={busy}
      onSave={() => {
        setBusy(true);
        changeCredential(connectionId, secret.key, value)
          .then((connection) => {
            setValue("");
            onSaved(connection);
          })
          .catch(onFailed)
          .finally(() => setBusy(false));
      }}
    />
  );
}
