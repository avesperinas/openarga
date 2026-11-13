import { CheckRow, Hint, List, Notice, Sheet, type Translate, useT } from "@openarga/ui";
import { useState } from "react";

import { type Ingredient, type Recipe, type ShoppingAdded, Unauthorised, addToShoppingList, signIn } from "./api";
import { quantityLabel } from "./units";

export function initiallyChosen(ingredients: Ingredient[]): number[] {
  return ingredients.filter((one) => !one.optional).map((one) => one.position);
}

export function summary(answer: ShoppingAdded, t: Translate): string {
  const already = answer.added.filter((one) => one.already_on_list).length;
  const fresh = answer.added.length - already;
  const parts = [];
  if (fresh > 0) parts.push(t(fresh === 1 ? "shopping.added.one" : "shopping.added.other", { count: fresh }));
  if (already > 0) parts.push(t(already === 1 ? "shopping.already.one" : "shopping.already.other", { count: already }));
  return parts.join(" · ");
}

export function ShoppingSheet({ recipe, onClose }: { recipe: Recipe; onClose: () => void }) {
  const t = useT();
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
        setProblem(t("shopping.failed"));
      })
      .finally(() => setSending(false));
  };

  if (answer) {
    return (
      <Sheet title={t("shopping.added_title")} onClose={onClose} action={{ label: t("common.done"), onClick: onClose }}>
        <Notice tone="positive" title={summary(answer, t)}>
          {t(answer.pending === 1 ? "shopping.pending.one" : "shopping.pending.other", { count: answer.pending })}
        </Notice>
      </Sheet>
    );
  }

  const count = chosen.length;
  return (
    <Sheet
      title={t("shopping.title")}
      onClose={onClose}
      action={{
        label: sending ? t("shopping.adding") : t("shopping.add", { count }),
        onClick: send,
        disabled: sending || count === 0,
      }}
    >
      <Hint>{t("shopping.for", { servings: recipe.requested_servings })}</Hint>
      <List>
        {ingredients.map((one) => (
          <CheckRow
            key={one.position}
            title={one.name}
            detail={`${quantityLabel(one.quantity, one.unit, t)}${one.optional ? ` · ${t("ingredient.optional")}` : ""}`}
            checked={chosen.includes(one.position)}
            onToggle={() => toggle(one.position)}
          />
        ))}
      </List>
      {problem && <Hint tone="warning" announce>{problem}</Hint>}
    </Sheet>
  );
}
