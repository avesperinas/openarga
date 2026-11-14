import { Button, Hint, List, ListRow, Screen, Section, Sheet, Switch, useT, useToast } from "@openarga/ui";
import { useEffect, useState } from "react";

import { ScreenHeader } from "./Header";
import { movementsText } from "./Products";
import { type RuleRow, api } from "./api";
import { capital } from "./format";

const ORIGIN: Record<string, string> = { merchant: "rules.origin_merchant" };

export function RulesScreen({ onBack, onChanged }: { onBack: () => void; onChanged: () => void }) {
  const t = useT();
  const [rules, setRules] = useState<RuleRow[] | null>(null);
  const [open, setOpen] = useState<RuleRow | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const load = () => api.rules().then(setRules, () => setProblem(t("rules.load_failed")));
  useEffect(() => {
    load();
  }, []);

  return (
    <Screen label={t("rules.title")}>
      <ScreenHeader title={t("rules.title")} back={{ label: t("tab.settings"), onClick: onBack }} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {rules && (
        <Section title={t("rules.in_order")} count={rules.length}>
          <List>
            {rules.map((r) => (
              <ListRow
                key={r.id}
                title={r.then}
                subtitle={capital(r.when)}
                value={movementsText(t, r.movements)}
                accessory="chevron-right"
                onClick={() => setOpen(r)}
              />
            ))}
          </List>
        </Section>
      )}
      <Hint>{t("rules.hint")}</Hint>
      {open && (
        <RuleSheet
          rule={open}
          onClose={() => setOpen(null)}
          onRemoved={() => {
            setOpen(null);
            load();
            onChanged();
          }}
        />
      )}
    </Screen>
  );
}

function RuleSheet({ rule, onClose, onRemoved }: { rule: RuleRow; onClose: () => void; onRemoved: () => void }) {
  const t = useT();
  const toast = useToast();
  const [keep, setKeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const remove = async () => {
    setBusy(true);
    try {
      const { kept } = await api.removeRule(rule.id, keep);
      toast({ message: kept ? t("rules.removed_kept", { movements: movementsText(t, kept) }) : t("rules.removed") });
      onRemoved();
    } catch {
      setProblem(t("rules.remove_failed"));
      setBusy(false);
    }
  };
  return (
    <Sheet title={rule.then} onClose={onClose}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <List>
        <ListRow title={t("rules.when")} subtitle={capital(rule.when)} />
        <ListRow title={t("rules.decides")} subtitle={rule.then} />
        <ListRow title={t("rules.explains")} value={movementsText(t, rule.movements)} />
        {rule.origin && ORIGIN[rule.origin] && <ListRow title={t("rules.origin")} subtitle={t(ORIGIN[rule.origin]!)} />}
      </List>
      {rule.movements > 0 && (
        <div className="money-switch-row">
          <span className="money-switch-text">
            <span>{t("rules.keep")}</span>
            <span className="money-switch-hint">
              {t("rules.keep_hint", { movements: movementsText(t, rule.movements) })}
            </span>
          </span>
          <Switch label={t("rules.keep")} checked={keep} onChange={setKeep} />
        </div>
      )}
      <Button variant="destructive" block disabled={busy} onClick={remove}>
        {t("rules.remove")}
      </Button>
      <Hint>{t("rules.remove_hint")}</Hint>
    </Sheet>
  );
}
