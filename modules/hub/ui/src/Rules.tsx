import { Button, Card, ChoiceChips, ConfirmDelete, Hint, List, ListRow, Sheet, TextField, regional } from "@openarga/ui";
import { useState } from "react";

import { type ConnectionDetail, type MailRule, type RuleFact, type RuleTrial, Refused, saveRules, tryRule } from "./api";
import { say } from "./words";

export const FACTS: { value: RuleFact; label: string }[] = [
  { value: "balance", get label() { return say("rules.fact.balance"); } },
  { value: "deposit", get label() { return say("rules.fact.deposit"); } },
  { value: "withdrawal", get label() { return say("rules.fact.withdrawal"); } },
];

export function ruleLine(rule: MailRule): string {
  const fact = FACTS.find((one) => one.value === rule.fact)?.label ?? rule.fact;
  return say("rules.line", { fact, anchor: rule.anchor });
}

export function trialLine(trial: RuleTrial): string {
  if (trial.problem) return say("rules.trial.problem", { problem: trial.problem });
  const amount = Number(trial.amount);
  return amount.toLocaleString(regional().locale, { style: "currency", currency: "EUR" });
}

export function ruleProblem(rule: MailRule): string | null {
  if (!rule.entity.trim()) return say("rules.missing.entity");
  if (!rule.product.trim()) return say("rules.missing.product");
  if (rule.sender.trim().length < 3) return say("rules.missing.sender");
  if (rule.anchor.trim().length < 2) return say("rules.missing.anchor");
  return null;
}

const EMPTY: MailRule = { entity: "", product: "", sender: "", subject: "", anchor: "", fact: "balance" };

export function MailRules({ connection, onChange }: { connection: ConnectionDetail; onChange: (next: ConnectionDetail) => void }) {
  const rules = connection.rules ?? [];
  const [editing, setEditing] = useState<{ rule: MailRule; index: number | null } | null>(null);

  return (
    <Card title={say("rules.title")}>
      {rules.length === 0 ? (
        <Hint>{say("rules.empty")}</Hint>
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
        {say("rules.add")}
      </Button>
      <Hint>{say("rules.forward")}</Hint>
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
      setProblem(error instanceof Refused ? error.message : say("rules.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      title={rule.entity ? `${rule.entity} · ${rule.product}` : say("rules.one")}
      onClose={onClose}
      action={{ label: say("rules.save"), disabled: busy, onClick: () => void run(() => onSave(draft)) }}
    >
      <TextField label={say("rules.entity")} placeholder="Finizens" value={draft.entity} onChange={set("entity")} autoFocus />
      <TextField
        label={say("rules.product")}
        placeholder={say("rules.product.placeholder")}
        value={draft.product}
        onChange={set("product")}
        hint={say("rules.product.hint")}
      />
      <TextField
        label={say("rules.sender")}
        placeholder="@finizens.com"
        value={draft.sender}
        onChange={set("sender")}
      />
      <TextField
        label={say("rules.subject")}
        placeholder={say("rules.optional")}
        value={draft.subject}
        onChange={set("subject")}
      />
      <TextField
        label={say("rules.anchor")}
        placeholder={say("rules.anchor.placeholder")}
        value={draft.anchor}
        onChange={set("anchor")}
        hint={say("rules.anchor.hint")}
      />
      <p className="hub-label">{say("rules.fact")}</p>
      <ChoiceChips label={say("rules.fact")} options={FACTS} value={draft.fact} onChange={set("fact")} />
      <Button
        disabled={busy}
        onClick={() => void run(async () => setTrials(await tryRule(connection.id, draft)))}
      >
        {say("rules.try")}
      </Button>
      {trials !== null &&
        (trials.length === 0 ? (
          <Hint>{say("rules.try.none")}</Hint>
        ) : (
          <List>
            {trials.map((trial, index) => (
              <ListRow
                key={index}
                title={trialLine(trial)}
                subtitle={`${trial.on ?? say("rules.undated")} · ${trial.subject}`}
                tone={trial.problem ? "warning" : undefined}
              />
            ))}
          </List>
        ))}
      {onRemove && (
        <Button variant="plain" disabled={busy} onClick={() => setConfirming(true)}>
          {say("rules.remove")}
        </Button>
      )}
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {confirming && onRemove && (
        <ConfirmDelete
          title={say("rules.remove.title")}
          subject={`${rule.entity} · ${rule.product}`}
          consequence={say("rules.remove.consequence")}
          action={say("rules.remove.action")}
          onCancel={() => setConfirming(false)}
          onConfirm={onRemove}
        />
      )}
    </Sheet>
  );
}
