import { Hint, List, ListRow, Sheet, TextField } from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import { type Provider, Refused, Unauthorised, connectBank, listBanks, readBankApp, signIn } from "./api";

const SHOWN_BANKS = 40;

export function matching(banks: string[], query: string): string[] {
  const plain = (text: string) =>
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  const wanted = plain(query.trim());
  return banks.filter((bank) => plain(bank).includes(wanted)).slice(0, SHOWN_BANKS);
}

export function oneAtATime<A extends unknown[], T>(
  run: (...args: A) => Promise<T>,
): (...args: A) => Promise<T> | null {
  let busy = false;
  return (...args) => {
    if (busy) return null;
    busy = true;
    return run(...args).catch((error: unknown) => {
      busy = false;
      throw error;
    });
  };
}

type Step = { name: "loading" } | { name: "app"; redirect: string } | { name: "banks"; banks: string[] };

export function BankSheet({ provider, onClose }: { provider: Provider; onClose: () => void }) {
  const [step, setStep] = useState<Step>({ name: "loading" });
  const [app, setApp] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [going, setGoing] = useState<string | null>(null);
  const start = useMemo(() => oneAtATime(connectBank), []);

  const failed = (error: unknown, otherwise: string) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Refused ? error.message : otherwise);
  };

  const showBanks = (secrets: Record<string, string>) =>
    listBanks(secrets)
      .then((banks) => setStep({ name: "banks", banks }))
      .catch((error: unknown) => failed(error, "No se pudo leer la lista de bancos."));

  useEffect(() => {
    readBankApp()
      .then(({ app: has, redirect_url }) =>
        has ? listBanks({}).then((banks) => setStep({ name: "banks", banks })) : setStep({ name: "app", redirect: redirect_url }),
      )
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Refused ? error.message : "No se pudo empezar.");
      });
  }, []);

  const choose = (bank: string) => {
    const started = start(bank, app);
    if (!started) return;
    setGoing(bank);
    setProblem(null);
    started
      .then((url) => window.location.assign(url))
      .catch((error: unknown) => {
        setGoing(null);
        failed(error, "No se pudo empezar.");
      });
  };

  const needsApp = step.name === "app";
  const complete = provider.secrets.every((secret) => app[secret.key]?.trim());

  return (
    <Sheet
      title="Conectar un banco"
      onClose={onClose}
      action={needsApp ? { label: "Ver los bancos", onClick: () => void showBanks(app), disabled: !complete } : undefined}
    >
      {step.name === "loading" && !problem && <Hint>Cargando…</Hint>}
      {needsApp && (
        <>
          <Hint>
            Arga lee tus cuentas por tu propia aplicación de Enable Banking. Dala de alta en su panel con{" "}
            <strong>{step.redirect}</strong> como dirección de vuelta, y pega aquí su id y su clave. Se guardan
            cifradas y valen para todos tus bancos.
          </Hint>
          {provider.secrets.map((secret) => (
            <TextField
              key={secret.key}
              label={secret.label}
              type="password"
              value={app[secret.key] ?? ""}
              onChange={(value) => setApp((current) => ({ ...current, [secret.key]: value }))}
              hint={secret.help}
            />
          ))}
        </>
      )}
      {step.name === "banks" && (
        <>
          <TextField label="Banco" type="search" value={query} onChange={setQuery} autoFocus placeholder="Busca el tuyo" />
          {going ? (
            <Hint announce>
              Abriendo {going}…
            </Hint>
          ) : (
            <List>
              {matching(step.banks, query).map((bank) => (
                <ListRow key={bank} title={bank} accessory="chevron-right" onClick={() => choose(bank)} />
              ))}
            </List>
          )}
        </>
      )}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
    </Sheet>
  );
}
