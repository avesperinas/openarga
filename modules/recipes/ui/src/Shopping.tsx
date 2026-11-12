import { CheckRow, Hint, List, Notice, Sheet } from "@openarga/ui";
import { useState } from "react";

import { type Ingredient, type Recipe, type ShoppingAdded, Unauthorised, addToShoppingList, signIn } from "./api";
import { quantityLabel } from "./units";

export function initiallyChosen(ingredients: Ingredient[]): number[] {
  return ingredients.filter((one) => !one.optional).map((one) => one.position);
}

export function summary(answer: ShoppingAdded): string {
  const already = answer.added.filter((one) => one.already_on_list).length;
  const fresh = answer.added.length - already;
  const parts = [];
  if (fresh > 0) parts.push(fresh === 1 ? "1 apuntado" : `${fresh} apuntados`);
  if (already > 0) parts.push(already === 1 ? "1 ya estaba" : `${already} ya estaban`);
  return parts.join(" · ");
}

export function ShoppingSheet({ recipe, onClose }: { recipe: Recipe; onClose: () => void }) {
  const ingredients = recipe.groups.flatMap((group) => group.ingredients);
  const [chosen, setChosen] = useState<number[]>(() => initiallyChosen(ingredients));
  const [sending, setSending] = useState(false);
  const [answer, setAnswer] = useState<ShoppingAdded | null>(null);
  const [problem, setProblem] = useState("");

  const toggle = (position: number) =>
    setChosen((now) => (now.includes(position) ? now.filter((one) => one !== position) : [...now, position]));

  const send = () => {
    setSending(true);
    setProblem("");
    addToShoppingList(recipe.id, { servings: recipe.requested_servings, positions: chosen })
      .then(setAnswer)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se ha podido apuntar en la lista. No se ha perdido nada: prueba otra vez.");
      })
      .finally(() => setSending(false));
  };

  if (answer) {
    return (
      <Sheet title="Añadido a la lista" onClose={onClose} action={{ label: "Hecho", onClick: onClose }}>
        <Notice tone="positive" title={summary(answer)}>
          {answer.pending === 1 ? "Hay 1 cosa en la lista." : `Hay ${answer.pending} cosas en la lista.`}
        </Notice>
      </Sheet>
    );
  }

  const count = chosen.length;
  return (
    <Sheet
      title="Añadir a la lista"
      onClose={onClose}
      action={{
        label: sending ? "Añadiendo…" : count === 1 ? "Añadir 1" : `Añadir ${count}`,
        onClick: send,
        disabled: sending || count === 0,
      }}
    >
      <Hint>Para {recipe.requested_servings}. Lo que ya esté en la lista se queda como está.</Hint>
      <List>
        {ingredients.map((one) => (
          <CheckRow
            key={one.position}
            title={one.name}
            detail={`${quantityLabel(one.quantity, one.unit)}${one.optional ? " · opcional" : ""}`}
            checked={chosen.includes(one.position)}
            onToggle={() => toggle(one.position)}
          />
        ))}
      </List>
      {problem && <Hint tone="warning" announce>{problem}</Hint>}
    </Sheet>
  );
}
