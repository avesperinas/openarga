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
import { ScreenHeader } from "./Header";
import { KitchenPlan, KitchenTimes } from "./Kitchen";
import { grams, kcal } from "./macros";
import { glyphOf, hueOf } from "./Recipes";
import { SharePicker } from "./SharePicker";
import { ShoppingSheet } from "./Shopping";
import { quantityLabel } from "./units";

export function RecipeScreen({ id, onBack, onEdit }: { id: string; onBack: () => void; onEdit: (id: string) => void }) {
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
      toast({ message: `Archivada · ${recipe.name}`, action: { label: "Deshacer", run: () => void unarchiveRecipe(recipe.id).then(changed) } });
      onBack();
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setSharing(error instanceof Error ? error.message : "No se ha podido archivar la receta.");
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
        <ScreenHeader back={{ label: "Recetario", onClick: onBack }} title="Receta" />
        <OfflineNotice />
        {found.error ? (
          <ErrorState title="No se pudo leer la receta" detail={found.error.message} onRetry={found.refresh} />
        ) : (
          <Skeleton label="Cargando la receta" />
        )}
      </Screen>
    );
  }

  return (
    <Screen>
      <ScreenHeader
        back={{ label: "Recetario", onClick: onBack }}
        eyebrow={recipe.versions > 1 ? `Versión ${recipe.version} de ${recipe.versions}` : undefined}
        title={recipe.name}
      />
      <OfflineNotice />

      {recipe.tags.length > 0 && (
        <Inline label="Etiquetas">
          {recipe.tags.map((tag) => (
            <Badge key={tag.id}>
              {tag.emoji && <span aria-hidden="true">{tag.emoji} </span>}
              {tag.name}
            </Badge>
          ))}
        </Inline>
      )}

      {recipe.archived && (
        <Notice tone="info" action={recipe.mine ? { label: "Sacar del archivo", onClick: () => void restore() } : undefined}>
          Archivada: no sale en el recetario.
        </Notice>
      )}
      <Banner hue={hueOf({ tags: recipe.tags.map((tag) => tag.name), name: recipe.name })} glyph={<Icon name={glyphOf(recipe.tags.map((tag) => tag.name))} />}>
        {recipe.kitchen.steps.length > 0 && <KitchenTimes kitchen={recipe.kitchen} />}
        <GroupLabel>Para cuántas personas</GroupLabel>
        <Stepper
          label="Para cuántas personas"
          value={recipe.requested_servings}
          step={1}
          min={1}
          max={50}
          inputMode="numeric"
          onChange={(value) => setServings(value ?? recipe.servings)}
        />
        {recipe.requested_servings !== recipe.servings && (
          <Hint>Escrita para {recipe.servings}. Las cantidades ya están ajustadas.</Hint>
        )}
      </Banner>

      <Section title="Ingredientes" count={recipe.groups.reduce((total, group) => total + group.ingredients.length, 0)}>
        {recipe.groups.map((group) => (
          <div key={group.category_id} className="recipes-group">
            <GroupLabel>
              <span aria-hidden="true">{group.emoji}</span> {group.name}
            </GroupLabel>
            <List>
              {group.ingredients.map((ingredient) => (
                <CheckRow
                  key={ingredient.position}
                  title={ingredient.name}
                  detail={ingredientDetail(ingredient)}
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

      <Section title="Por ración">
        <Macros recipe={recipe} />
        <Micros recipe={recipe} />
      </Section>

      <Inline label="Acciones">
        <Button variant="tinted" icon="basket" onClick={() => setShopping(true)}>
          Añadir a la lista
        </Button>
        <Button icon="edit" onClick={() => onEdit(recipe.id)}>
          Editar
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
              setSharing(error instanceof Error ? error.message : "No se ha podido compartir la receta.");
            }
          }}
        />
        {recipe.mine && !recipe.archived && (
          <Button icon="box" onClick={() => void archive()}>
            Archivar
          </Button>
        )}
        {recipe.mine && (
          <Button variant="destructive" icon="trash" onClick={() => setDeleting(true)}>
            Borrar
          </Button>
        )}
      </Inline>
      {sharing && <Hint tone="warning">{sharing}</Hint>}
      {shopping && <ShoppingSheet recipe={recipe} onClose={() => setShopping(false)} />}
      {deleting && (
        <ConfirmDelete
          title="¿Borrar esta receta?"
          subject={recipe.name}
          consequence={deleteConsequence(recipe)}
          action="Borrar receta"
          onCancel={() => setDeleting(false)}
          onConfirm={() =>
            deleteRecipe(recipe.id)
              .then(() => {
                changed();
                onBack();
              })
              .catch((error: unknown) => {
                if (error instanceof Unauthorised) return signIn();
                throw new Error("No se ha podido borrar la receta.");
              })
          }
        />
      )}
      <AppVersion />
    </Screen>
  );
}

export function ingredientDetail(ingredient: Pick<Recipe["groups"][number]["ingredients"][number], "quantity" | "unit" | "note" | "optional" | "food_id">): string {
  return [
    quantityLabel(ingredient.quantity, ingredient.unit),
    ingredient.note,
    ingredient.optional ? "opcional" : null,
    ingredient.food_id === null ? "sin macros" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function deleteConsequence(recipe: Pick<Recipe, "versions" | "groups">): string {
  const ingredients = recipe.groups.reduce((total, group) => total + group.ingredients.length, 0);
  const parts = [];
  if (ingredients === 1) parts.push("su ingrediente");
  if (ingredients > 1) parts.push(`sus ${ingredients} ingredientes`);
  if (recipe.versions > 1) parts.push(`sus ${recipe.versions} versiones`);
  return `${parts.length ? `Se borra con ${parts.join(" y ")}` : "Se borra"}. No se puede deshacer.`;
}

export function Macros({ recipe }: { recipe: Recipe }) {
  const each = recipe.nutrition.per_serving;
  return (
    <Card>
      <Figures
        label="Por ración"
        items={[
          { label: "kcal", value: kcal(each.kcal), lit: true },
          { label: "g proteína", value: grams(each.protein) },
          { label: "g grasa", value: grams(each.fat) },
          { label: "g hidratos", value: grams(each.carbs) },
        ]}
      />
      <SplitBar label="De dónde salen las kcal" parts={kcalSplit(each)} />
      <Hint>{totalLine(recipe)}</Hint>
      {recipe.nutrition.uncertainty && (
        <Hint tone="warning">{recipe.nutrition.uncertainty}</Hint>
      )}
    </Card>
  );
}

export function totalLine(recipe: Pick<Recipe, "requested_servings" | "nutrition">): string {
  const total = recipe.nutrition.total;
  const head = recipe.requested_servings > 1 ? `Receta entera (${recipe.requested_servings} raciones)` : "Receta entera";
  return `${head}: ${kcal(total.kcal)} kcal · ${grams(total.protein)} g proteína · ${grams(total.fat)} g grasa · ${grams(total.carbs)} g hidratos`;
}

export function kcalSplit(macros: Pick<Recipe["nutrition"]["per_serving"], "protein" | "fat" | "carbs">) {
  const parts = [
    { label: "Proteína", kcal: macros.protein * 4, hue: 1 as const },
    { label: "Grasa", kcal: macros.fat * 9, hue: 3 as const },
    { label: "Hidratos", kcal: macros.carbs * 4, hue: 2 as const },
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
    <Collapsible title="Micronutrientes" subtitle={`${rows.length} por ración`}>
      <KeyFigures
        label="Micronutrientes por ración"
        items={rows.map(({ info, value, partial }) => ({
          label: info.name,
          value: `${grams(value)} ${info.unit}`,
          foot: partial ? "dato incompleto" : undefined,
        }))}
      />
      {partial > 0 && (
        <Hint>
          Los atenuados salen de menos del 80 % de la receta: algún ingrediente no trae ese dato.
        </Hint>
      )}
    </Collapsible>
  );
}
