import { duration, Figures, Hint, RecipeGrid, Section, StepItem, StepList } from "@openarga/ui";
import { useState } from "react";

import type { Ingredient, Kitchen } from "./api";
import { ACTIONS, EQUIPMENT, whenLabel } from "./steps";
import { quantityLabel } from "./units";

export function KitchenTimes({ kitchen }: { kitchen: Pick<Kitchen, "total_minutes" | "active_minutes"> }) {
  return (
    <Figures
      label="Cuánto lleva"
      items={[
        { label: "De principio a fin", value: duration(kitchen.total_minutes) },
        { label: "Tú delante", value: duration(kitchen.active_minutes), lit: true },
      ]}
    />
  );
}

export function KitchenPlan({ kitchen, ingredients }: { kitchen: Kitchen; ingredients: Ingredient[] }) {
  const [done, setDone] = useState<number[]>([]);
  if (kitchen.steps.length === 0) {
    return (
      <Section title="En la cocina">
        <Hint>
          Esta receta todavía no tiene pasos. Con ellos sale el diagrama y el tiempo que lleva.
        </Hint>
      </Section>
    );
  }

  const amounts = new Map(ingredients.map((one) => [one.position, one]));
  const note = (minutes: number, attended: boolean) =>
    attended ? duration(minutes) : `${duration(minutes)} · corre solo`;

  return (
    <Section title="En la cocina">
      <div className="surface recipes-panel">
        <RecipeGrid
          label="Qué se junta con qué"
          columns={kitchen.grid.columns}
          rows={kitchen.grid.rows.map((row) => {
            const found = amounts.get(row.position);
            return {
              id: row.position,
              label: row.name,
              amount: found ? quantityLabel(found.quantity, found.unit) : undefined,
              unused: row.orphan,
            };
          })}
          cells={kitchen.grid.cells.map((cell) => ({
            id: cell.position,
            label: ACTIONS[cell.action] ?? cell.action,
            detail: cell.text,
            note: note(cell.minutes, cell.attended),
            column: cell.column,
            row: cell.row,
            span: cell.span,
            attended: cell.attended,
          }))}
          bands={kitchen.grid.bands.map((band) => ({
            id: band.position,
            label: `${ACTIONS[band.action] ?? band.action}: ${band.text}`,
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
            Los pasos {clash.positions.join(" y ")} piden{" "}
            {(EQUIPMENT[clash.equipment] ?? clash.equipment).toLowerCase()} a la vez.
          </Hint>
        ))}
      </div>

      <StepList label="Pasos">
        {kitchen.steps.map((step, index) => (
          <StepItem
            key={step.position}
            number={index + 1}
            when={whenLabel(step.start, step.end)}
            text={step.text}
            detail={[
              `${ACTIONS[step.action] ?? step.action} · ${duration(step.minutes)}`,
              ...(step.attended ? [] : ["corre solo"]),
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
