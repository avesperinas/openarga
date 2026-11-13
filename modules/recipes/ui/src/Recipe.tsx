import { mutate, useResource } from "@openarga/app";
import {
  Badge,
  Banner,
  Button,
  Card,
  CheckRow,
  Collapsible,
  ConfirmDelete,
  ErrorState,
  Figures,
  GroupLabel,
  Hint,
  Icon,
  Inline,
  KeyFigures,
  List,
  Notice,
  OfflineNotice,
  Screen,
  Section,
  Skeleton,
  SplitBar,
  Stepper,
  type Translate,
  useT,
  useToast,
} from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type NutrientInfo,
  type Recipe,
  Unauthorised,
  archiveRecipe,
  changed,
  deleteRecipe,
  unarchiveRecipe,
  readNutrients,
  readRecipe,
  readSpaces,
  shareRecipe,
  signIn,
} from "./api";
import { categoryName } from "./categories";
import { ScreenHeader } from "./Header";
import { KitchenPlan, KitchenTimes } from "./Kitchen";
import { grams, kcal } from "./macros";
import { glyphOf, hueOf } from "./Recipes";
import { SharePicker } from "./SharePicker";
import { ShoppingSheet } from "./Shopping";
import { quantityLabel } from "./units";

export function RecipeScreen({ id, onBack, onEdit }: { id: string; onBack: () => void; onEdit: (id: string) => void }) {
  const t = useT();
  const [servings, setServings] = useState<number | null>(null);
  const key = `recipe:${id}:${servings ?? ""}`;
  const found = useResource(key, () => readRecipe(id, servings ?? undefined), { persist: servings === null });
  const shown = useRef<Recipe | null>(null);
  if (found.data) shown.current = found.data;
  const recipe = found.data ?? (found.error ? null : shown.current);
  const setRecipe = (next: Recipe) => void mutate(key, next);
  const [deleting, setDeleting] = useState(false);
  const [shopping, setShopping] = useState(false);
  const toast = useToast();
  const archive = async () => {
    if (!recipe) return;
    try {
      await archiveRecipe(recipe.id);
      changed();
      toast({ message: t("recipe.archived_toast", { name: recipe.name }), action: { label: t("common.undo"), run: () => void unarchiveRecipe(recipe.id).then(changed) } });
      onBack();
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setSharing(error instanceof Error ? error.message : t("recipe.archive_failed"));
    }
  };
  const restore = async () => {
    if (!recipe) return;
    await unarchiveRecipe(recipe.id);
    changed();
    setRecipe({ ...recipe, archived: false });
  };
  const spaces = useResource("spaces", readSpaces).data ?? [];
  const [sharing, setSharing] = useState("");
  const [ready, setReady] = useState<number[]>([]);

  if (!recipe) {
    return (
      <Screen>
        <ScreenHeader back={{ label: t("tabs.recipes"), onClick: onBack }} title={t("recipe.title")} />
        <OfflineNotice />
        {found.error ? (
          <ErrorState title={t("recipe.read_failed")} detail={found.error.message} onRetry={found.refresh} />
        ) : (
          <Skeleton label={t("recipe.loading")} />
        )}
      </Screen>
    );
  }

  return (
    <Screen>
      <ScreenHeader
        back={{ label: t("tabs.recipes"), onClick: onBack }}
        eyebrow={recipe.versions > 1 ? t("recipe.version", { version: recipe.version, of: recipe.versions }) : undefined}
        title={recipe.name}
      />
      <OfflineNotice />

      {recipe.tags.length > 0 && (
        <Inline label={t("recipe.tags")}>
          {recipe.tags.map((tag) => (
            <Badge key={tag.id}>
              {tag.emoji && <span aria-hidden="true">{tag.emoji} </span>}
              {tag.name}
            </Badge>
          ))}
        </Inline>
      )}

      {recipe.archived && (
        <Notice tone="info" action={recipe.mine ? { label: t("recipe.unarchive"), onClick: () => void restore() } : undefined}>
          {t("recipe.archived_notice")}
        </Notice>
      )}
      <Banner hue={hueOf({ tags: recipe.tags.map((tag) => tag.name), name: recipe.name })} glyph={<Icon name={glyphOf(recipe.tags.map((tag) => tag.name))} />}>
        {recipe.kitchen.steps.length > 0 && <KitchenTimes kitchen={recipe.kitchen} />}
        <GroupLabel>{t("recipe.how_many")}</GroupLabel>
        <Stepper
          label={t("recipe.how_many")}
          value={recipe.requested_servings}
          step={1}
          min={1}
          max={50}
          inputMode="numeric"
          onChange={(value) => setServings(value ?? recipe.servings)}
        />
        {recipe.requested_servings !== recipe.servings && (
          <Hint>{t("recipe.written_for", { servings: recipe.servings })}</Hint>
        )}
      </Banner>

      <Section title={t("recipe.ingredients")} count={recipe.groups.reduce((total, group) => total + group.ingredients.length, 0)}>
        {recipe.groups.map((group) => (
          <div key={group.category_id} className="recipes-group">
            <GroupLabel>
              <span aria-hidden="true">{group.emoji}</span> {categoryName(t, group.category_id, group.name)}
            </GroupLabel>
            <List>
              {group.ingredients.map((ingredient) => (
                <CheckRow
                  key={ingredient.position}
                  title={ingredient.name}
                  detail={ingredientDetail(ingredient, t)}
                  checked={ready.includes(ingredient.position)}
                  onToggle={() =>
                    setReady((now) =>
                      now.includes(ingredient.position)
                        ? now.filter((one) => one !== ingredient.position)
                        : [...now, ingredient.position],
                    )
                  }
                />
              ))}
            </List>
          </div>
        ))}
      </Section>

      <KitchenPlan
        kitchen={recipe.kitchen}
        ingredients={recipe.groups.flatMap((group) => group.ingredients)}
      />

      <Section title={t("recipe.per_serving")}>
        <Macros recipe={recipe} />
        <Micros recipe={recipe} />
      </Section>

      <Inline label={t("recipe.actions")}>
        <Button variant="tinted" icon="basket" onClick={() => setShopping(true)}>
          {t("shopping.title")}
        </Button>
        <Button icon="edit" onClick={() => onEdit(recipe.id)}>
          {t("recipe.edit")}
        </Button>
        <SharePicker
          recipe={recipe}
          spaces={spaces}
          onChoose={async (spaceId) => {
            try {
              setRecipe(await shareRecipe(recipe.id, spaceId));
              changed();
              setSharing("");
            } catch (error) {
              if (error instanceof Unauthorised) return signIn();
              setSharing(error instanceof Error ? error.message : t("recipe.share_failed"));
            }
          }}
        />
        {recipe.mine && !recipe.archived && (
          <Button icon="box" onClick={() => void archive()}>
            {t("recipe.archive")}
          </Button>
        )}
        {recipe.mine && (
          <Button variant="destructive" icon="trash" onClick={() => setDeleting(true)}>
            {t("common.delete")}
          </Button>
        )}
      </Inline>
      {sharing && <Hint tone="warning">{sharing}</Hint>}
      {shopping && <ShoppingSheet recipe={recipe} onClose={() => setShopping(false)} />}
      {deleting && (
        <ConfirmDelete
          title={t("recipe.delete_title")}
          subject={recipe.name}
          consequence={deleteConsequence(recipe, t)}
          action={t("recipe.delete")}
          onCancel={() => setDeleting(false)}
          onConfirm={() =>
            deleteRecipe(recipe.id)
              .then(() => {
                changed();
                onBack();
              })
              .catch((error: unknown) => {
                if (error instanceof Unauthorised) return signIn();
                throw new Error(t("recipe.delete_failed"));
              })
          }
        />
      )}
      <AppVersion />
    </Screen>
  );
}

export function ingredientDetail(
  ingredient: Pick<Recipe["groups"][number]["ingredients"][number], "quantity" | "unit" | "note" | "optional" | "food_id">,
  t: Translate,
): string {
  return [
    quantityLabel(ingredient.quantity, ingredient.unit, t),
    ingredient.note,
    ingredient.optional ? t("ingredient.optional") : null,
    ingredient.food_id === null ? t("ingredient.no_macros") : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function deleteConsequence(recipe: Pick<Recipe, "versions" | "groups">, t: Translate): string {
  const ingredients = recipe.groups.reduce((total, group) => total + group.ingredients.length, 0);
  const parts = [];
  if (ingredients === 1) parts.push(t("delete.its_ingredient"));
  if (ingredients > 1) parts.push(t("delete.its_ingredients", { count: ingredients }));
  if (recipe.versions > 1) parts.push(t("delete.its_versions", { count: recipe.versions }));
  return parts.length ? t("delete.with", { what: parts.join(t("common.and")) }) : t("delete.alone");
}

export function Macros({ recipe }: { recipe: Recipe }) {
  const t = useT();
  const each = recipe.nutrition.per_serving;
  return (
    <Card>
      <Figures
        label={t("recipe.per_serving")}
        items={[
          { label: "kcal", value: kcal(each.kcal), lit: true },
          { label: t("figure.protein"), value: grams(each.protein) },
          { label: t("figure.fat"), value: grams(each.fat) },
          { label: t("figure.carbs"), value: grams(each.carbs) },
        ]}
      />
      <SplitBar label={t("recipe.kcal_from")} parts={kcalSplit(each, t)} />
      <Hint>{totalLine(recipe, t)}</Hint>
      {recipe.nutrition.uncertainty && (
        <Hint tone="warning">{recipe.nutrition.uncertainty}</Hint>
      )}
    </Card>
  );
}

export function totalLine(recipe: Pick<Recipe, "requested_servings" | "nutrition">, t: Translate): string {
  const total = recipe.nutrition.total;
  const head =
    recipe.requested_servings > 1 ? t("total.whole_servings", { count: recipe.requested_servings }) : t("total.whole");
  return t("total.line", {
    head,
    kcal: kcal(total.kcal),
    protein: grams(total.protein),
    fat: grams(total.fat),
    carbs: grams(total.carbs),
  });
}

export function kcalSplit(macros: Pick<Recipe["nutrition"]["per_serving"], "protein" | "fat" | "carbs">, t: Translate) {
  const parts = [
    { label: t("nutrient.protein"), kcal: macros.protein * 4, hue: 1 as const },
    { label: t("nutrient.fat"), kcal: macros.fat * 9, hue: 3 as const },
    { label: t("nutrient.carbs"), kcal: macros.carbs * 4, hue: 2 as const },
  ];
  const total = parts.reduce((sum, part) => sum + part.kcal, 0);
  return parts.map((part) => ({
    label: part.label,
    value: total > 0 ? `${Math.round((part.kcal / total) * 100)} %` : "–",
    share: part.kcal,
    hue: part.hue,
  }));
}

export const ENOUGH_COVERAGE = 0.8;
const MACRO_KEYS = new Set(["kcal", "protein", "fat", "carbs"]);

export function microRows(
  recipe: Pick<Recipe, "nutrition">,
  list: NutrientInfo[],
): { info: NutrientInfo; value: number; partial: boolean }[] {
  const values = recipe.nutrition.nutrients ?? {};
  const coverage = recipe.nutrition.coverage ?? {};
  return list
    .filter((info) => info.front && !MACRO_KEYS.has(info.key) && values[info.key] !== undefined)
    .map((info) => ({
      info,
      value: values[info.key] ?? 0,
      partial: (coverage[info.key] ?? 1) < ENOUGH_COVERAGE,
    }));
}

export function Micros({ recipe }: { recipe: Recipe }) {
  const t = useT();
  const [list, setList] = useState<NutrientInfo[]>([]);
  useEffect(() => {
    readNutrients()
      .then(setList)
      .catch(() => setList([]));
  }, []);
  const rows = microRows(recipe, list);
  if (rows.length === 0) return null;
  const partial = rows.filter((row) => row.partial).length;
  return (
    <Collapsible title={t("micros.title")} subtitle={t("micros.count", { count: rows.length })}>
      <KeyFigures
        label={t("micros.label")}
        items={rows.map(({ info, value, partial }) => ({
          label: t(`nutrient.${info.key}`),
          value: `${grams(value)} ${info.unit}`,
          foot: partial ? t("micros.partial") : undefined,
        }))}
      />
      {partial > 0 && (
        <Hint>{t("micros.partial_hint")}</Hint>
      )}
    </Collapsible>
  );
}
