import { Card, ConfirmChange, Hint, List, ListRow, StatRow, StatTile, useToast } from "@openarga/ui";
import { useState } from "react";

import { type Expenditure, type Proposal, saveGoal } from "./api";
import { amount } from "./words";

export function proposalPurpose(one: Pick<Proposal, "rate_kg_week">): string {
  if (one.rate_kg_week === 0) return "Para mantener el peso";
  const verb = one.rate_kg_week < 0 ? "bajar" : "subir";
  return `Para ${verb} ${amount(Math.abs(one.rate_kg_week))} kg por semana`;
}

export function proposalLabel(one: Proposal): string {
  return `${proposalPurpose(one)}, ${amount(one.kcal, 0)} kcal`;
}

export function proposalRange(kcal: number): { min: number; max: number } {
  return { min: Math.round((kcal * 0.95) / 10) * 10, max: Math.round((kcal * 1.05) / 10) * 10 };
}

export function changeLabel(kgWeek: number | null): string {
  if (kgWeek === null) return "";
  if (Math.abs(kgWeek) < 0.05) return "el peso, igual";
  return `${kgWeek > 0 ? "+" : "−"}${amount(Math.abs(kgWeek))} kg por semana`;
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
  const [asking, setAsking] = useState<Proposal | null>(null);
  const toast = useToast();
  const proposals = only === undefined ? found.proposals : found.proposals.filter((one) => one.rate_kg_week === only);
  return (
    <Card title={only === undefined ? "Gasto estimado" : "La propuesta del lunes"}>
      {found.kcal === null ? (
        <Hint>Aún no se puede saber: {found.missing}.</Hint>
      ) : (
        <>
          {only === undefined && (
            <StatRow label="Gasto estimado">
              <StatTile label="Al día" value={`${amount(found.kcal, 0)} kcal`} />
              <StatTile label="Comido" value={`${amount(found.intake ?? 0, 0)} kcal`} />
              <StatTile label="Peso" value={changeLabel(found.weight_change_kg_week)} />
            </StatRow>
          )}
          <Hint>
            De {found.days} días completos de las cuatro últimas semanas. Nunca por debajo de tu metabolismo basal (
            {amount(found.bmr ?? 0, 0)} kcal).
          </Hint>
          <List>
            {proposals.map((one) => (
              <ListRow
                key={one.rate_kg_week}
                title={`${amount(one.kcal, 0)} kcal al día`}
                subtitle={`${proposalPurpose(one)} · ${one.floored ? "subida hasta tu metabolismo basal" : "¿Lo pongo?"}`}
                action={{ icon: "done", label: `Poner ${amount(one.kcal, 0)} kcal`, onClick: () => setAsking(one) }}
              />
            ))}
          </List>
        </>
      )}
      {asking && (
        <ConfirmChange
          title="¿Cambiar el objetivo de kcal?"
          changes={[
            {
              label: "Kcal al día",
              from: kcalGoal ? `${amount(kcalGoal, 0)} kcal` : "sin objetivo",
              to: `${amount(proposalRange(asking.kcal).min, 0)} – ${amount(proposalRange(asking.kcal).max, 0)} kcal`,
            },
          ]}
          detail="Desde hoy. Lo de antes se sigue midiendo con lo que había."
          action="Poner el objetivo"
          onCancel={() => setAsking(null)}
          onConfirm={() =>
            saveGoal("kcal", { ...proposalRange(asking.kcal), unit: "amount", profile: "any" }).then(() => {
              setAsking(null);
              toast({ message: "Objetivo de kcal puesto desde hoy" });
              onChanged();
            })
          }
        />
      )}
    </Card>
  );
}
