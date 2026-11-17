import {
  Button,
  Card,
  ConfirmDelete,
  CredentialField,
  DateField,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Screen,
  Sheet,
  TextField,
  regional,
  zonedDates,
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
  typePrice,
} from "./api";
import { TokenSheet } from "./Add";
import { ScreenHeader } from "./Header";
import { Pending, changed, useLoad } from "./Loads";
import { say } from "./words";

export function when(iso: string): string {
  return zonedDates({ day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

const day = (iso: string) => zonedDates({ day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));

const list = (items: string[]) => new Intl.ListFormat(regional().locale, { type: "conjunction" }).format(items);

export function runLine(run: Run): string {
  switch (run.outcome) {
    case "ok":
      if (run.operation === "search") return say("run.answered");
      if (run.operation === "run") return run.detail ?? say("run.done");
      if (run.emitted === 0) return say("run.ok.none");
      return say(run.emitted === 1 ? "run.ok.one" : "run.ok", { n: run.emitted });
    case "error":
      return run.detail ? say("run.failed.detail", { detail: run.detail }) : say("run.failed");
    case "rate_limited":
      return say("run.rate_limited");
    case "skipped":
      return run.detail ? say("run.skipped.detail", { detail: run.detail }) : say("run.skipped");
    case "running":
      return say("run.running");
  }
}

export function budgetLine(budget: NonNullable<ConnectionDetail["budget"]>): string {
  if (budget.remaining === 0) return say("budget.spent", { limit: budget.limit });
  return say("budget.left", { remaining: budget.remaining, limit: budget.limit });
}

const SESSIONS = ["race", "qualifying", "sprint", "sprint_qualifying", "practice"];

export function calendarLine(connection: Pick<ConnectionDetail, "provider" | "settings">): string | null {
  const settings = connection.settings ?? {};
  if (connection.provider === "holidays") {
    const country = String(settings.country ?? "");
    return settings.region
      ? say("calendar.holidays.region", { country, region: String(settings.region) })
      : say("calendar.holidays", { country });
  }
  if (connection.provider === "formula1") {
    const chosen = Array.isArray(settings.sessions) ? settings.sessions : [];
    const names = chosen.map((key) => (SESSIONS.includes(key) ? say(`calendar.f1.${key}`) : key));
    return say("calendar.f1", { sessions: list(names) });
  }
  if (connection.provider === "football") {
    return settings.team_name
      ? say("calendar.football", { team: String(settings.team_name) })
      : say("calendar.football.any");
  }
  if (connection.provider === "ical" && typeof settings.url === "string") {
    try {
      return say("calendar.ical", { host: new URL(settings.url).host });
    } catch {
      return null;
    }
  }
  if (connection.provider === "ical_private") return say("calendar.ical_private");
  return null;
}

export function landsIn(connection: Pick<ConnectionDetail, "inlets">): string | null {
  const apps = [...new Set((connection.inlets ?? []).map((inlet) => inlet.app))];
  if (apps.length === 0) return null;
  return say("lands_in", { apps: list(apps) });
}

export function removeConsequence(connection: ConnectionDetail): string {
  return say("remove.consequence", { provider: connection.provider_name });
}

export function labelHint(): string {
  return say("add.name.hint");
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
    if (params.get("bank") === "connected") return say("returned.bank.connected");
    if (params.get("bank") === "no-accounts") return say("returned.bank.no_accounts");
    if (params.get("google") === "connected") return say("returned.google.connected");
    return null;
  });

  const failed = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Refused ? error.message : say("save.failed"));
  }, []);

  const show = (next: ConnectionDetail) => {
    setProblem(null);
    set(next);
  };

  if (!connection) {
    return (
      <Screen>
        <ScreenHeader back={{ label: say("tabs.status"), onClick: onBack }} title={say("connection")} />
        <OfflineNotice />
        <Pending found={found} />
      </Screen>
    );
  }

  return (
    <Screen>
      <ScreenHeader
        back={{ label: say("tabs.status"), onClick: onBack }}
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
          {connection.last_ok_at ? say("last_ok", { when: when(connection.last_ok_at) }) : say("nothing_yet")}
          {connection.emitted_week > 0 && ` ${say("this_week", { n: connection.emitted_week })}`}
        </Hint>
      </Card>

      {said && (
        <Hint announce>
          {said}
        </Hint>
      )}

      {(connection.authorizes || connection.budget) && (
        <Card title={say("access")}>
          {connection.consent_expires_at && connection.state !== "expired" && (
            <Hint>{say("access.until", { day: day(connection.consent_expires_at) })}</Hint>
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
                      setSaid(updated.outcome === "ok" ? say("sync.done") : say("sync.failed", { detail: updated.outcome_detail ?? updated.outcome }));
                    })
                    .catch(failed)
                    .finally(() => setSyncing(false));
                }}
              >
                {syncing ? say("sync.running") : say("sync.now")}
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
                {say("reconnect")}
              </Button>
            )}
          </div>
          {connection.accounts && connection.accounts.length > 0 && (
            <List>
              {connection.accounts.map((account, index) => (
                <ListRow
                  key={`${account.name}-${index}`}
                  title={account.name ?? say("account")}
                  detail={account.iban_tail ? `…${account.iban_tail}` : undefined}
                />
              ))}
            </List>
          )}
        </Card>
      )}

      {connection.provider === "prices" && <TypedPrice />}
      {(calendarLine(connection) || landsIn(connection)) && (
        <Card title={say("brings")}>
          {calendarLine(connection) && <Hint>{calendarLine(connection)}</Hint>}
          {landsIn(connection) && <Hint>{landsIn(connection)}</Hint>}
        </Card>
      )}

      <Card title={say("runs")}>
        {connection.runs.length === 0 ? (
          <Hint>
            {connection.paused
              ? say("runs.paused")
              : say("runs.none")}
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
        <Card title={say("token.card")}>
          <Hint>{say("token.card.hint")}</Hint>
          <Button variant="tinted" onClick={() => renewToken(connection.id).then((renewed) => setToken(renewed.ingest_token)).catch(failed)}>
            {say("token.renew")}
          </Button>
        </Card>
      )}
      {token && <TokenSheet token={token} onDone={() => setToken(null)} />}

      {connection.secrets.length > 0 && <Card title={say("credentials")}>
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
        <Button onClick={onBack}>{say("back")}</Button>
        <Button
          variant="tinted"
          onClick={() =>
            (connection.paused ? resumeConnection : pauseConnection)(connection.id).then(show).catch(failed)
          }
        >
          {connection.paused ? say("resume") : say("pause")}
        </Button>
        <Button variant="plain" icon="edit" onClick={() => setRenaming(true)}>
          {say("rename")}
        </Button>
        <Button variant="destructive" icon="trash" onClick={() => setRemoving(true)}>
          {say("rules.remove.action")}
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
          title={say("remove.title")}
          subject={connection.label}
          consequence={removeConsequence(connection)}
          action={say("remove.action")}
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

export function priceProblem(instrument: string, price: string): string | null {
  if (!instrument.trim()) return say("price.missing.instrument");
  const value = Number(price.replace(",", "."));
  if (!Number.isFinite(value) || value <= 0) return say("price.missing.price");
  return null;
}

function TypedPrice() {
  const [instrument, setInstrument] = useState("");
  const [on, setOn] = useState(new Date().toISOString().slice(0, 10));
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const save = () => {
    const wrong = priceProblem(instrument, price);
    if (wrong) return setProblem(wrong);
    setBusy(true);
    setProblem(null);
    typePrice({ instrument: instrument.trim(), on, price: price.replace(",", ".") })
      .then((done) => {
        setSaid(say(done.new ? "price.saved" : "price.known", { symbol: done.symbol, on: done.on }));
        setPrice("");
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Refused ? error.message : say("save.failed"));
      })
      .finally(() => setBusy(false));
  };

  return (
    <Card title={say("price.title")}>
      <Hint>{say("price.hint")}</Hint>
      <TextField label={say("price.instrument")} value={instrument} onChange={setInstrument} placeholder="IE00B4L5Y983, VWCE.DE" />
      <DateField label={say("price.on")} value={on} onChange={(day) => day && setOn(day)} />
      <TextField
        label={say("price.value")}
        value={price}
        onChange={setPrice}
        onSubmit={save}
        inputMode="decimal"
        hint={problem ?? said ?? undefined}
        invalid={problem !== null}
      />
      <Button onClick={save} disabled={busy}>
        {say("price.save")}
      </Button>
    </Card>
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
        setProblem(error instanceof Refused ? error.message : say("save.failed"));
      })
      .finally(() => setBusy(false));
  };

  return (
    <Sheet title={say("rename")} onClose={onClose} action={{ label: say("rules.save"), onClick: save, disabled: busy || !label.trim() }}>
      <TextField
        label={say("add.name")}
        value={label}
        onChange={setLabel}
        onSubmit={save}
        autoFocus
        hint={problem ?? labelHint()}
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
