import { Card, ConfirmChange, Hint, List, ListRow, StatRow, StatTile, type Translate, useT, useToast } from "@openarga/ui";
import { useState } from "react";

import { type Expenditure, type Proposal, saveGoal } from "./api";
import { amount } from "./words";

export function proposalPurpose(one: Pick<Proposal, "rate_kg_week">, t: Translate): string {
  if (one.rate_kg_week === 0) return t("proposal.keep");
  return t(one.rate_kg_week < 0 ? "proposal.lose" : "proposal.gain", { kg: amount(Math.abs(one.rate_kg_week)) });
}

export function proposalLabel(one: Proposal, t: Translate): string {
  return `${proposalPurpose(one, t)}, ${amount(one.kcal, 0)} kcal`;
}

export function proposalRange(kcal: number): { min: number; max: number } {
  return { min: Math.round((kcal * 0.95) / 10) * 10, max: Math.round((kcal * 1.05) / 10) * 10 };
}

export function changeLabel(kgWeek: number | null, t: Translate): string {
  if (kgWeek === null) return "";
  if (Math.abs(kgWeek) < 0.05) return t("expenditure.same_weight");
  return t("expenditure.per_week", { kg: `${kgWeek > 0 ? "+" : "−"}${amount(Math.abs(kgWeek))}` });
}

export function ExpenditureCard({
  found,
  kcalGoal,
  onChanged,
  only,
}: {
  found: Expenditure;
  kcalGoal: number | null;
  onChanged: () => void;
  only?: number;
}) {
  const t = useT();
  const [asking, setAsking] = useState<Proposal | null>(null);
  const toast = useToast();
  const proposals = only === undefined ? found.proposals : found.proposals.filter((one) => one.rate_kg_week === only);
  return (
    <Card title={only === undefined ? t("expenditure.title") : t("expenditure.monday")}>
      {found.kcal === null ? (
        <Hint>{t("expenditure.not_yet", { missing: found.missing ?? "" })}</Hint>
      ) : (
        <>
          {only === undefined && (
            <StatRow label={t("expenditure.title")}>
              <StatTile label={t("expenditure.per_day")} value={`${amount(found.kcal, 0)} kcal`} />
              <StatTile label={t("expenditure.eaten")} value={`${amount(found.intake ?? 0, 0)} kcal`} />
              <StatTile label={t("expenditure.weight")} value={changeLabel(found.weight_change_kg_week, t)} />
            </StatRow>
          )}
          <Hint>
            {t("expenditure.from_days", { days: found.days, bmr: amount(found.bmr ?? 0, 0) })}
          </Hint>
          <List>
            {proposals.map((one) => (
              <ListRow
                key={one.rate_kg_week}
                title={t("expenditure.kcal_day", { kcal: amount(one.kcal, 0) })}
                subtitle={`${proposalPurpose(one, t)} · ${one.floored ? t("expenditure.floored") : t("expenditure.set_it")}`}
                action={{ icon: "done", label: t("expenditure.set_kcal", { kcal: amount(one.kcal, 0) }), onClick: () => setAsking(one) }}
              />
            ))}
          </List>
        </>
      )}
      {asking && (
        <ConfirmChange
          title={t("expenditure.confirm_title")}
          changes={[
            {
              label: t("expenditure.kcal_per_day"),
              from: kcalGoal ? `${amount(kcalGoal, 0)} kcal` : t("goal.none"),
              to: `${amount(proposalRange(asking.kcal).min, 0)} – ${amount(proposalRange(asking.kcal).max, 0)} kcal`,
            },
          ]}
          detail={t("goal.from_today")}
          action={t("goal.set")}
          onCancel={() => setAsking(null)}
          onConfirm={() =>
            saveGoal("kcal", { ...proposalRange(asking.kcal), unit: "amount", profile: "any" }).then(() => {
              setAsking(null);
              toast({ message: t("expenditure.done") });
              onChanged();
            })
          }
        />
      )}
    </Card>
  );
}
