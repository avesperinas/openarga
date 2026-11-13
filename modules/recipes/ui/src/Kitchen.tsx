import { duration, Figures, Hint, RecipeGrid, Section, StepItem, StepList, useT } from "@openarga/ui";
import { useState } from "react";

import type { Ingredient, Kitchen } from "./api";
import { actionName, equipmentName, whenLabel } from "./steps";
import { quantityLabel } from "./units";

export function KitchenTimes({ kitchen }: { kitchen: Pick<Kitchen, "total_minutes" | "active_minutes"> }) {
  const t = useT();
  return (
    <Figures
      label={t("kitchen.how_long")}
      items={[
        { label: t("kitchen.total"), value: duration(kitchen.total_minutes) },
        { label: t("kitchen.active"), value: duration(kitchen.active_minutes), lit: true },
      ]}
    />
  );
}

export function KitchenPlan({ kitchen, ingredients }: { kitchen: Kitchen; ingredients: Ingredient[] }) {
  const t = useT();
  const [done, setDone] = useState<number[]>([]);
  if (kitchen.steps.length === 0) {
    return (
      <Section title={t("kitchen.title")}>
        <Hint>{t("kitchen.no_steps")}</Hint>
      </Section>
    );
  }

  const amounts = new Map(ingredients.map((one) => [one.position, one]));
  const note = (minutes: number, attended: boolean) =>
    attended ? duration(minutes) : `${duration(minutes)} · ${t("kitchen.runs_alone")}`;

  return (
    <Section title={t("kitchen.title")}>
      <div className="surface recipes-panel">
        <RecipeGrid
          label={t("kitchen.grid")}
          columns={kitchen.grid.columns}
          rows={kitchen.grid.rows.map((row) => {
            const found = amounts.get(row.position);
            return {
              id: row.position,
              label: row.name,
              amount: found ? quantityLabel(found.quantity, found.unit, t) : undefined,
              unused: row.orphan,
            };
          })}
          cells={kitchen.grid.cells.map((cell) => ({
            id: cell.position,
            label: actionName(t, cell.action),
            detail: cell.text,
            note: note(cell.minutes, cell.attended),
            column: cell.column,
            row: cell.row,
            span: cell.span,
            attended: cell.attended,
          }))}
          bands={kitchen.grid.bands.map((band) => ({
            id: band.position,
            label: `${actionName(t, band.action)}: ${band.text}`,
            note: note(band.minutes, band.attended),
          }))}
        />

        {kitchen.grid.notes.map((said) => (
          <Hint key={said}>
            {said}
          </Hint>
        ))}
        {kitchen.overlaps.map((clash) => (
          <Hint key={clash.equipment} tone="warning">
            {t("kitchen.clash", {
              steps: clash.positions.join(t("common.and")),
              equipment: equipmentName(t, clash.equipment).toLowerCase(),
            })}
          </Hint>
        ))}
      </div>

      <StepList label={t("kitchen.steps")}>
        {kitchen.steps.map((step, index) => (
          <StepItem
            key={step.position}
            number={index + 1}
            when={whenLabel(step.start, step.end, t)}
            text={step.text}
            detail={[
              `${actionName(t, step.action)} · ${duration(step.minutes)}`,
              ...(step.attended ? [] : [t("kitchen.runs_alone")]),
              ...(step.ingredients.length > 0 ? [step.ingredients.join(", ")] : []),
            ].join(" · ")}
            done={done.includes(step.position)}
            next={step.position === kitchen.steps.find((one) => !done.includes(one.position))?.position}
            onToggle={() =>
              setDone((now) =>
                now.includes(step.position) ? now.filter((one) => one !== step.position) : [...now, step.position],
              )
            }
          />
        ))}
      </StepList>
    </Section>
  );
}
