import {
  CopyField,
  Hint,
  InletSettings,
  type InletValues,
  Sheet,
  type SourceAnswers,
  SourceQuestions,
  TextField,
  inletValues,
  proposedSourceName,
  sourceMissing,
  sourceParams,
} from "@openarga/ui";
import { useCallback, useState } from "react";

import { type Provider, Refused, Unauthorised, createConnection, searchOffer, signIn } from "./api";
import { BankSheet } from "./BankSheet";
import { say } from "./words";

export function missing(provider: Provider, values: Record<string, string>): string[] {
  return provider.secrets.filter((secret) => !values[secret.key]?.trim()).map((secret) => secret.label);
}

export function plugsOf(provider: Provider, chosen: Record<string, InletValues>, name: string): Record<string, InletValues> {
  return Object.fromEntries(
    (provider.inlets ?? []).map((inlet) => [inlet.key, inletValues(inlet.settings, chosen[inlet.key] ?? {}, name, provider.offer?.tone ?? 1)]),
  );
}

export function AddFor({
  provider,
  onClose,
  onCreated,
}: {
  provider: Provider;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  if (provider.authorizes) return <BankSheet provider={provider} onClose={onClose} />;
  if (provider.offer) return <PlugSheet provider={provider} onClose={onClose} onCreated={onCreated} />;
  return <AddSheet provider={provider} onClose={onClose} onCreated={onCreated} />;
}

export function AddSheet({
  provider,
  onClose,
  onCreated,
}: {
  provider: Provider;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [label, setLabel] = useState(provider.name);
  const [values, setValues] = useState<Record<string, string>>({});
  const [settings, setSettings] = useState<Record<string, string>>(() =>
    Object.fromEntries((provider.settings ?? []).map((setting) => [setting.key, setting.default])),
  );
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [issued, setIssued] = useState<{ id: string; token: string } | null>(null);

  const connect = () => {
    setBusy(true);
    setProblem(null);
    createConnection(provider.id, label, values, settings)
      .then((created) => {
        if (created.authorization_url) return window.location.assign(created.authorization_url);
        return created.ingest_token ? setIssued({ id: created.id, token: created.ingest_token }) : onCreated(created.id);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Refused ? error.message : say("add.failed"));
        setBusy(false);
      });
  };

  if (issued) return <TokenSheet token={issued.token} onDone={() => onCreated(issued.id)} />;

  return (
    <Sheet
      title={say("add.title", { name: provider.name })}
      onClose={onClose}
      action={{
        label: busy ? say("add.connecting") : say("add.connect"),
        onClick: connect,
        disabled: busy || missing(provider, values).length > 0,
      }}
    >
      <Hint>{provider.description}</Hint>
      <TextField label={say("add.name")} value={label} onChange={setLabel} hint={say("add.name.hint")} />
      {(provider.settings ?? []).map((setting) => (
        <TextField
          key={setting.key}
          label={setting.label}
          value={settings[setting.key] ?? ""}
          onChange={(value) => setSettings((current) => ({ ...current, [setting.key]: value }))}
          hint={setting.help}
        />
      ))}
      {provider.secrets.map((secret) => (
        <TextField
          key={secret.key}
          label={secret.label}
          type="password"
          value={values[secret.key] ?? ""}
          onChange={(value) => setValues((current) => ({ ...current, [secret.key]: value }))}
          hint={secret.help}
        />
      ))}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      <Hint>{say("add.encrypted")}</Hint>
    </Sheet>
  );
}

export function PlugSheet({
  provider,
  onClose,
  onCreated,
}: {
  provider: Provider;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const offer = provider.offer!;
  const [answers, setAnswers] = useState<SourceAnswers>({});
  const [label, setLabel] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, InletValues>>({});
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const search = useCallback(
    (ask: string, query?: string, parent?: string) => searchOffer(provider.id, ask, query, parent),
    [provider.id],
  );

  const name = label ?? proposedSourceName(offer, answers);
  const plugs = plugsOf(provider, chosen, name);

  const connect = () => {
    const lacks = sourceMissing(offer.asks, answers);
    if (lacks) return setProblem(lacks);
    setBusy(true);
    setProblem(null);
    createConnection(provider.id, name, {}, sourceParams(offer.asks, answers), plugs)
      .then((created) => onCreated(created.id))
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Refused ? error.message : say("add.failed"));
        setBusy(false);
      });
  };

  return (
    <Sheet title={offer.title} onClose={onClose} action={{ label: busy ? say("add.connecting") : say("add.connect"), onClick: connect, disabled: busy }}>
      <Hint>{provider.description}</Hint>
      <SourceQuestions asks={offer.asks} answers={answers} onChange={setAnswers} search={search} onError={setProblem} />
      <TextField label={say("add.name")} value={name} onChange={setLabel} hint={say("add.name.here")} />
      {(provider.inlets ?? []).map((inlet) => (
        <InletSettings
          key={inlet.key}
          title={say("add.inlet", { app: inlet.app })}
          settings={inlet.settings}
          values={plugs[inlet.key] ?? {}}
          onChange={(values) => setChosen((current) => ({ ...current, [inlet.key]: values }))}
        />
      ))}
      {problem && <Hint tone="warning">{problem}</Hint>}
    </Sheet>
  );
}

export const PUSH_URL = `${typeof window === "undefined" ? "" : window.location.origin}/api/hub/push/apple-health`;

export function TokenSheet({ token, onDone }: { token: string; onDone: () => void }) {
  return (
    <Sheet title={say("token.title")} onClose={onDone} action={{ label: say("done"), onClick: onDone }}>
      <Hint>{say("token.hint")}</Hint>
      <CopyField label={say("token.token")} value={token} />
      <CopyField label={say("token.address")} value={PUSH_URL} />
    </Sheet>
  );
}
