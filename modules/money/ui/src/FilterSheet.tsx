import { Button, CheckChips, Collapsible, GroupLabel, Sheet, TextField, type Translate, useT } from "@openarga/ui";
import { useState } from "react";

import type { State, Status } from "./api";
import { type Filters, NO_FILTERS, type What } from "./filters";
import { amountText, currencySymbol, natureName, ownershipName, parseAmount, statusName, typeName } from "./format";

type Option<T extends string> = { value: T; label: string };

function summary<T extends string>(t: Translate, values: T[], options: Option<T>[]): string | undefined {
  if (!values.length) return undefined;
  const names = options.filter((o) => values.includes(o.value)).map((o) => o.label);
  return names.length <= 2 ? names.join(", ") : t("filter.marked", { count: names.length });
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
  const t = useT();
  const [draft, setDraft] = useState(filters);
  const [min, setMin] = useState(filters.min !== null ? amountText(filters.min) : "");
  const [max, setMax] = useState(filters.max !== null ? amountText(filters.max) : "");

  const what: Option<What>[] = [
    { value: "expense", label: t("filter.expenses") },
    { value: "income", label: t("filter.incomes") },
    { value: "transfer", label: t("filter.transfers") },
    { value: "other", label: t("filter.other") },
  ];
  const ownership: Option<"individual" | "shared">[] = [
    { value: "individual", label: ownershipName("individual") },
    { value: "shared", label: ownershipName("shared") },
  ];
  const institutions = [...new Set(state.accounts.map((a) => a.institution))].sort().map((name) => ({ value: name, label: name }));
  const types = [...new Map(state.accounts.map((a) => [a.type, a.type_label])).entries()].map(([value, label]) => ({ value, label: typeName(value, label) }));
  const accounts = [
    ...state.accounts.filter((a) => a.movements !== "manual").map((a) => ({ value: a.key, label: a.name })),
    { value: "@other", label: t("account.outside") },
  ];
  const statuses: Option<Status>[] = [
    { value: "ask", label: statusName("ask") },
    { value: "pending", label: statusName("pending") },
    { value: "default", label: t("filter.default") },
    { value: "manual", label: t("filter.manual") },
    { value: "auto", label: statusName("auto") },
  ];
  const groups = (["expense", "income"] as const).flatMap((nature) =>
    (["individual", "shared"] as const)
      .map((own) => ({
        key: `${nature}/${own}`,
        label: `${natureName(nature)} ${ownershipName(own).toLowerCase()}`,
        options: state.categories.filter((c) => c.nature === nature && c.ownership === own).map((c) => ({ value: c.id, label: c.name })),
      }))
      .filter((g) => g.options.length > 0),
  );
  const allCategories = groups.flatMap((g) => g.options);
  const symbol = currencySymbol();
  const amount =
    [min && t("filter.from_amount", { amount: `${min} ${symbol}` }), max && t("filter.to_amount", { amount: `${max} ${symbol}` })].filter(Boolean).join(" · ") ||
    undefined;

  const apply = () => {
    onChange({ ...draft, min: min ? parseAmount(min) : null, max: max ? parseAmount(max) : null });
    onClose();
  };

  return (
    <Sheet title={t("filter.title")} onClose={onClose} action={{ label: t("filter.see"), onClick: apply }}>
      <div className="money-filters">
        <Collapsible title={t("filter.kind")} subtitle={summary(t, draft.what, what)}>
          <CheckChips<What> label={t("filter.kind")} values={draft.what} onChange={(v) => setDraft({ ...draft, what: v })} options={what} />
        </Collapsible>
        <Collapsible title={t("filter.whose")} subtitle={summary(t, draft.ownership, ownership)}>
          <CheckChips<"individual" | "shared"> label={t("filter.whose")} values={draft.ownership} onChange={(v) => setDraft({ ...draft, ownership: v })} options={ownership} />
        </Collapsible>
        <Collapsible title={t("filter.category")} subtitle={summary(t, draft.categories, allCategories)}>
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
        <Collapsible title={t("filter.institution")} subtitle={summary(t, draft.institutions, institutions)}>
          <CheckChips<string> label={t("filter.institution")} values={draft.institutions} onChange={(v) => setDraft({ ...draft, institutions: v })} options={institutions} />
        </Collapsible>
        <Collapsible title={t("filter.account_type")} subtitle={summary(t, draft.accountTypes, types)}>
          <CheckChips<string> label={t("filter.account_type")} values={draft.accountTypes} onChange={(v) => setDraft({ ...draft, accountTypes: v })} options={types} />
        </Collapsible>
        <Collapsible title={t("filter.account")} subtitle={summary(t, draft.accounts, accounts)}>
          <CheckChips<string> label={t("filter.account")} values={draft.accounts} onChange={(v) => setDraft({ ...draft, accounts: v })} options={accounts} />
        </Collapsible>
        <Collapsible title={t("filter.status")} subtitle={summary(t, draft.statuses, statuses)}>
          <CheckChips<Status> label={t("filter.status")} values={draft.statuses} onChange={(v) => setDraft({ ...draft, statuses: v })} options={statuses} />
        </Collapsible>
        <Collapsible title={t("filter.amount")} subtitle={amount}>
          <div className="money-pair">
            <TextField label={t("filter.min")} value={min} onChange={setMin} inputMode="decimal" placeholder={amountText(0)} invalid={!!min && parseAmount(min) === null} />
            <TextField label={t("filter.max")} value={max} onChange={setMax} inputMode="decimal" placeholder={t("filter.no_limit")} invalid={!!max && parseAmount(max) === null} />
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
          {t("filter.clear")}
        </Button>
      </div>
    </Sheet>
  );
}
