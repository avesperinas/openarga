import { Button, Hint, List, ListRow, Screen, Section, Sheet, Switch, useToast } from "@openarga/ui";
import { useEffect, useState } from "react";

import { ScreenHeader } from "./Header";
import { movementsText } from "./Products";
import { type RuleRow, api } from "./api";
import { capital } from "./format";

const ORIGIN: Record<string, string> = { merchant: "De «aplicar a todo el comercio»" };

export function RulesScreen({ onBack, onChanged }: { onBack: () => void; onChanged: () => void }) {
  const [rules, setRules] = useState<RuleRow[] | null>(null);
  const [open, setOpen] = useState<RuleRow | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const load = () => api.rules().then(setRules, () => setProblem("No se han podido cargar."));
  useEffect(() => {
    load();
  }, []);

  return (
    <Screen label="Reglas">
      <ScreenHeader title="Reglas" back={{ label: "Ajustes", onClick: onBack }} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {rules && (
        <Section title="En orden: la primera que casa, decide" count={rules.length}>
          <List>
            {rules.map((r) => (
              <ListRow
                key={r.id}
                title={r.then}
                subtitle={capital(r.when)}
                value={movementsText(r.movements)}
                accessory="chevron-right"
                onClick={() => setOpen(r)}
              />
            ))}
          </List>
        </Section>
      )}
      <Hint>Lo que etiquetas a mano manda sobre cualquier regla. Una regla se crea con «aplicar a todo el comercio» en un movimiento.</Hint>
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
  const toast = useToast();
  const [keep, setKeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const remove = async () => {
    setBusy(true);
    try {
      const { kept } = await api.removeRule(rule.id, keep);
      toast({ message: kept ? `Regla quitada · ${movementsText(kept)} se quedan como estaban` : "Regla quitada" });
      onRemoved();
    } catch {
      setProblem("No se ha podido quitar.");
      setBusy(false);
    }
  };
  return (
    <Sheet title={rule.then} onClose={onClose}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <List>
        <ListRow title="Cuándo" subtitle={capital(rule.when)} />
        <ListRow title="Qué decide" subtitle={rule.then} />
        <ListRow title="Explica hoy" value={movementsText(rule.movements)} />
        {rule.origin && ORIGIN[rule.origin] && <ListRow title="De dónde sale" subtitle={ORIGIN[rule.origin]} />}
      </List>
      {rule.movements > 0 && (
        <div className="money-switch-row">
          <span className="money-switch-text">
            <span>Dejar como están</span>
            <span className="money-switch-hint">
              Los {movementsText(rule.movements)} que explica se quedan etiquetados así. Apagado, vuelven a interpretarse sin ella.
            </span>
          </span>
          <Switch label="Dejar como están" checked={keep} onChange={setKeep} />
        </div>
      )}
      <Button variant="destructive" block disabled={busy} onClick={remove}>
        Quitar la regla
      </Button>
      <Hint>Deja de aplicarse a lo que llegue a partir de ahora.</Hint>
    </Sheet>
  );
}
