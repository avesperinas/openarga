import { Button, CheckChips, Collapsible, GroupLabel, Sheet, TextField } from "@openarga/ui";
import { useState } from "react";

import type { State, Status } from "./api";
import { type Filters, NO_FILTERS, type What } from "./filters";
import { NATURE, OWNERSHIP, amountText, parseAmount } from "./format";

type Option<T extends string> = { value: T; label: string };

function summary<T extends string>(values: T[], options: Option<T>[]): string | undefined {
  if (!values.length) return undefined;
  const names = options.filter((o) => values.includes(o.value)).map((o) => o.label);
  return names.length <= 2 ? names.join(", ") : `${names.length} marcadas`;
}

export function FilterSheet({
  state,
  filters,
  onChange,
  onClose,
}: {
  state: State;
  filters: Filters;
  onChange: (f: Filters) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(filters);
  const [min, setMin] = useState(filters.min !== null ? amountText(filters.min) : "");
  const [max, setMax] = useState(filters.max !== null ? amountText(filters.max) : "");

  const what: Option<What>[] = [
    { value: "expense", label: "Gastos" },
    { value: "income", label: "Ingresos" },
    { value: "transfer", label: "Traspasos" },
    { value: "other", label: "Otros" },
  ];
  const ownership: Option<"individual" | "shared">[] = [
    { value: "individual", label: "Individual" },
    { value: "shared", label: "Compartido" },
  ];
  const institutions = [...new Set(state.accounts.map((a) => a.institution))].sort().map((name) => ({ value: name, label: name }));
  const types = [...new Map(state.accounts.map((a) => [a.type, a.type_label])).entries()].map(([value, label]) => ({ value, label }));
  const accounts = [
    ...state.accounts.filter((a) => a.movements !== "manual").map((a) => ({ value: a.key, label: a.name })),
    { value: "@other", label: "Fuera de cuenta" },
  ];
  const statuses: Option<Status>[] = [
    { value: "ask", label: "Por etiquetar" },
    { value: "pending", label: "Sin interpretar" },
    { value: "default", label: "Por defecto" },
    { value: "manual", label: "A mano" },
    { value: "auto", label: "Automático" },
  ];
  const groups = (["expense", "income"] as const).flatMap((nature) =>
    (["individual", "shared"] as const)
      .map((own) => ({
        key: `${nature}/${own}`,
        label: `${NATURE[nature]} ${OWNERSHIP[own].toLowerCase()}`,
        options: state.categories.filter((c) => c.nature === nature && c.ownership === own).map((c) => ({ value: c.id, label: c.name })),
      }))
      .filter((g) => g.options.length > 0),
  );
  const allCategories = groups.flatMap((g) => g.options);
  const amount = [min && `desde ${min} €`, max && `hasta ${max} €`].filter(Boolean).join(" · ") || undefined;

  const apply = () => {
    onChange({ ...draft, min: min ? parseAmount(min) : null, max: max ? parseAmount(max) : null });
    onClose();
  };

  return (
    <Sheet title="Filtros" onClose={onClose} action={{ label: "Ver resultados", onClick: apply }}>
      <div className="money-filters">
        <Collapsible title="Tipo de movimiento" subtitle={summary(draft.what, what)}>
          <CheckChips<What> label="Tipo de movimiento" values={draft.what} onChange={(v) => setDraft({ ...draft, what: v })} options={what} />
        </Collapsible>
        <Collapsible title="De quién" subtitle={summary(draft.ownership, ownership)}>
          <CheckChips<"individual" | "shared"> label="De quién" values={draft.ownership} onChange={(v) => setDraft({ ...draft, ownership: v })} options={ownership} />
        </Collapsible>
        <Collapsible title="Categoría" subtitle={summary(draft.categories, allCategories)}>
          <div className="money-filter-groups">
            {groups.map((g) => (
              <div key={g.key} className="money-filter-group">
              <GroupLabel>{g.label}</GroupLabel>
              <CheckChips<string>
                label={g.label}
                values={draft.categories.filter((id) => g.options.some((o) => o.value === id))}
                onChange={(ids) =>
                  setDraft({ ...draft, categories: [...draft.categories.filter((id) => !g.options.some((o) => o.value === id)), ...ids] })
                }
                options={g.options}
              />
              </div>
            ))}
          </div>
        </Collapsible>
        <Collapsible title="Entidad" subtitle={summary(draft.institutions, institutions)}>
          <CheckChips<string> label="Entidad" values={draft.institutions} onChange={(v) => setDraft({ ...draft, institutions: v })} options={institutions} />
        </Collapsible>
        <Collapsible title="Tipo de cuenta" subtitle={summary(draft.accountTypes, types)}>
          <CheckChips<string> label="Tipo de cuenta" values={draft.accountTypes} onChange={(v) => setDraft({ ...draft, accountTypes: v })} options={types} />
        </Collapsible>
        <Collapsible title="Cuenta" subtitle={summary(draft.accounts, accounts)}>
          <CheckChips<string> label="Cuenta" values={draft.accounts} onChange={(v) => setDraft({ ...draft, accounts: v })} options={accounts} />
        </Collapsible>
        <Collapsible title="Estado" subtitle={summary(draft.statuses, statuses)}>
          <CheckChips<Status> label="Estado" values={draft.statuses} onChange={(v) => setDraft({ ...draft, statuses: v })} options={statuses} />
        </Collapsible>
        <Collapsible title="Importe" subtitle={amount}>
          <div className="money-pair">
            <TextField label="Desde" value={min} onChange={setMin} inputMode="decimal" placeholder="0,00" invalid={!!min && parseAmount(min) === null} />
            <TextField label="Hasta" value={max} onChange={setMax} inputMode="decimal" placeholder="Sin límite" invalid={!!max && parseAmount(max) === null} />
          </div>
        </Collapsible>
        <Button
          variant="plain"
          onClick={() => {
            setDraft({ ...NO_FILTERS, text: filters.text });
            setMin("");
            setMax("");
          }}
        >
          Quitar todos los filtros
        </Button>
      </div>
    </Sheet>
  );
}
