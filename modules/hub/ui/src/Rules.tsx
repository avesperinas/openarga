import { Button, Card, ChoiceChips, ConfirmDelete, Hint, List, ListRow, Sheet, TextField } from "@openarga/ui";
import { useState } from "react";

import { type ConnectionDetail, type MailRule, type RuleFact, type RuleTrial, Refused, saveRules, tryRule } from "./api";

export const FACTS: { value: RuleFact; label: string }[] = [
  { value: "balance", label: "Lo que vale" },
  { value: "deposit", label: "Una aportación" },
  { value: "withdrawal", label: "Una retirada" },
];

export function ruleLine(rule: MailRule): string {
  const fact = FACTS.find((one) => one.value === rule.fact)?.label ?? rule.fact;
  return `${fact}, tras «${rule.anchor}»`;
}

export function trialLine(trial: RuleTrial): string {
  if (trial.problem) return `No lo entiende: ${trial.problem}`;
  const amount = Number(trial.amount);
  return amount.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
}

export function ruleProblem(rule: MailRule): string | null {
  if (!rule.entity.trim()) return "Falta la entidad.";
  if (!rule.product.trim()) return "Falta el producto.";
  if (rule.sender.trim().length < 3) return "Falta el remitente, o una parte de su dirección.";
  if (rule.anchor.trim().length < 2) return "Falta el texto que va justo antes del importe.";
  return null;
}

const EMPTY: MailRule = { entity: "", product: "", sender: "", subject: "", anchor: "", fact: "balance" };

export function MailRules({ connection, onChange }: { connection: ConnectionDetail; onChange: (next: ConnectionDetail) => void }) {
  const rules = connection.rules ?? [];
  const [editing, setEditing] = useState<{ rule: MailRule; index: number | null } | null>(null);

  return (
    <Card title="Reglas">
      {rules.length === 0 ? (
        <Hint>
          Todavía ninguna. Una regla dice de quién es un correo y dónde está su importe: el valor de tu cartera, o
          lo que aportaste.
        </Hint>
      ) : (
        <List>
          {rules.map((rule, index) => (
            <ListRow
              key={rule.id ?? index}
              title={`${rule.entity} · ${rule.product}`}
              subtitle={ruleLine(rule)}
              accessory="chevron-right"
              onClick={() => setEditing({ rule, index })}
            />
          ))}
        </List>
      )}
      <Button block icon="plus" onClick={() => setEditing({ rule: EMPTY, index: null })}>
        Añadir una regla
      </Button>
      <Hint>
        Reenvía los correos con un filtro automático: el día de cada dato es el del correo que llega al buzón.
      </Hint>
      {editing && (
        <RuleSheet
          connection={connection}
          rule={editing.rule}
          onClose={() => setEditing(null)}
          onSave={async (rule) => {
            const next =
              editing.index === null ? [...rules, rule] : rules.map((one, i) => (i === editing.index ? rule : one));
            onChange(await saveRules(connection.id, next));
            setEditing(null);
          }}
          onRemove={
            editing.index === null
              ? undefined
              : async () => {
                  onChange(await saveRules(connection.id, rules.filter((_, i) => i !== editing.index)));
                  setEditing(null);
                }
          }
        />
      )}
    </Card>
  );
}

function RuleSheet({
  connection,
  rule,
  onClose,
  onSave,
  onRemove,
}: {
  connection: ConnectionDetail;
  rule: MailRule;
  onClose: () => void;
  onSave: (rule: MailRule) => Promise<void>;
  onRemove?: () => Promise<void>;
}) {
  const [draft, setDraft] = useState<MailRule>(rule);
  const [trials, setTrials] = useState<RuleTrial[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const set = (key: keyof MailRule) => (value: string) => {
    setDraft({ ...draft, [key]: value });
    setTrials(null);
  };

  const run = async (work: () => Promise<void>) => {
    const missing = ruleProblem(draft);
    if (missing) return setProblem(missing);
    setBusy(true);
    setProblem(null);
    try {
      await work();
    } catch (error) {
      setProblem(error instanceof Refused ? error.message : "No se ha podido. Vuelve a intentarlo.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      title={rule.entity ? `${rule.entity} · ${rule.product}` : "Una regla"}
      onClose={onClose}
      action={{ label: "Guardar", disabled: busy, onClick: () => void run(() => onSave(draft)) }}
    >
      <TextField label="Entidad" placeholder="Finizens" value={draft.entity} onChange={set("entity")} autoFocus />
      <TextField
        label="Producto"
        placeholder="Plan de pensiones"
        value={draft.product}
        onChange={set("product")}
        hint="Dos reglas con la misma entidad y el mismo producto son el mismo producto en Money."
      />
      <TextField
        label="El remitente contiene"
        placeholder="@finizens.com"
        value={draft.sender}
        onChange={set("sender")}
      />
      <TextField
        label="El asunto contiene"
        placeholder="Opcional"
        value={draft.subject}
        onChange={set("subject")}
      />
      <TextField
        label="Texto justo antes del importe"
        placeholder="Valor de tu cartera"
        value={draft.anchor}
        onChange={set("anchor")}
        hint="Cópialo del correo tal cual. Si un correo no lo trae, la pasada falla y te lo dice."
      />
      <p className="hub-label">Ese importe es</p>
      <ChoiceChips label="Ese importe es" options={FACTS} value={draft.fact} onChange={set("fact")} />
      <Button
        disabled={busy}
        onClick={() => void run(async () => setTrials(await tryRule(connection.id, draft)))}
      >
        Probar con los correos del buzón
      </Button>
      {trials !== null &&
        (trials.length === 0 ? (
          <Hint>Ningún correo de los últimos seis meses casa con el remitente y el asunto.</Hint>
        ) : (
          <List>
            {trials.map((trial, index) => (
              <ListRow
                key={index}
                title={trialLine(trial)}
                subtitle={`${trial.on ?? "Sin fecha"} · ${trial.subject}`}
                tone={trial.problem ? "warning" : undefined}
              />
            ))}
          </List>
        ))}
      {onRemove && (
        <Button variant="plain" disabled={busy} onClick={() => setConfirming(true)}>
          Quitar esta regla
        </Button>
      )}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {confirming && onRemove && (
        <ConfirmDelete
          title="¿Quitar la regla?"
          subject={`${rule.entity} · ${rule.product}`}
          consequence="Sus correos dejan de leerse. Lo que ya trajo se queda en Money."
          action="Quitar"
          onCancel={() => setConfirming(false)}
          onConfirm={onRemove}
        />
      )}
    </Sheet>
  );
}
