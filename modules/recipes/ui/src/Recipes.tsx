import { useResource } from "@openarga/app";
import {
  Badge,
  Inline,
  Collapsible,
  ChoiceChips,
  CreateButton,
  duration,
  EmptyState,
  ErrorState,
  Icon,
  type IconName,
  OfflineNotice,
  Screen,
  SearchField,
  Skeleton,
  Tile,
  type TileHue,
  Tiles,
  toneOf,
} from "@openarga/ui";
import { useMemo, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Category, type RecipeSummary, readArchived, readCategories, readRecipes } from "./api";
import { ScreenHeader } from "./Header";

export function RecipesScreen({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const found = useResource("recipes", readRecipes, { persist: true });
  const categories = useResource("categories", readCategories, { persist: true }).data ?? [];
  const recipes = found.data;
  const archived = useResource("recipes:archived", readArchived).data ?? [];
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState(ALL);
  const tags = useMemo(() => tagsByUse(recipes ?? []).slice(0, 6), [recipes]);
  const shown = useMemo(() => filtered(recipes ?? [], query, tag), [recipes, query, tag]);

  return (
    <Screen>
      <ScreenHeader title="Recetario" />
      <OfflineNotice />
      {found.loading && <Skeleton label="Cargando las recetas" />}
      {!recipes && found.error && (
        <ErrorState title="No se pudo leer el recetario" detail={found.error.message} onRetry={found.refresh} />
      )}
      {recipes && recipes.length === 0 && <Empty categories={categories} onNew={onNew} />}
      {recipes && recipes.length > 0 && (
        <>
          <SearchField label="Buscar en el recetario" placeholder="Buscar una receta" value={query} onChange={setQuery} />
          {tags.length > 1 && (
            <ChoiceChips
              label="Etiqueta"
              value={tag}
              onChange={setTag}
              options={[{ value: ALL, label: "Todas" }, ...tags.map((one) => ({ value: one, label: one }))]}
            />
          )}
          {shown.length > 0 ? (
            <Grid recipes={shown} onOpen={onOpen} />
          ) : (
            <EmptyState icon="search" title="Ninguna receta así">
              Prueba con otra palabra o quita la etiqueta.
            </EmptyState>
          )}
        </>
      )}
      {archived.length > 0 && (
        <Collapsible title={`Archivadas (${archived.length})`} subtitle="No salen en el recetario ni al buscar en Macros">
          <Grid recipes={archived} onOpen={onOpen} muted />
        </Collapsible>
      )}
      {recipes && <CreateButton label="Receta" onClick={onNew} />}
      <AppVersion />
    </Screen>
  );
}

const ALL = "";

export function tagsByUse(recipes: RecipeSummary[]): string[] {
  const uses = new Map<string, number>();
  for (const recipe of recipes) for (const tag of recipe.tags) uses.set(tag, (uses.get(tag) ?? 0) + 1);
  return [...uses].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "es")).map(([tag]) => tag);
}

const fold = (text: string) =>
  text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLocaleLowerCase("es");

export function filtered(recipes: RecipeSummary[], query: string, tag: string): RecipeSummary[] {
  const wanted = fold(query.trim());
  return recipes.filter(
    (recipe) =>
      (tag === ALL || recipe.tags.includes(tag)) &&
      (!wanted || fold(recipe.name).includes(wanted) || recipe.tags.some((one) => fold(one).includes(wanted))),
  );
}

export function face(recipe: Pick<RecipeSummary, "total_minutes" | "active_minutes">): { figure?: string; caption?: string } {
  const { total_minutes: total, active_minutes: active } = recipe;
  if (total === null || active === null) return {};
  if (total === 0) return { figure: "al momento" };
  if (active === 0) return { figure: "sin faena", caption: `${duration(total)} en total` };
  if (active === total) return { figure: duration(total), caption: "en total" };
  return { figure: duration(active), caption: "tú delante" };
}

export function detailOf(recipe: RecipeSummary): string {
  const parts = [`Para ${recipe.servings} ${recipe.servings === 1 ? "persona" : "personas"}`];
  const { total_minutes: total, active_minutes: active } = recipe;
  if (total !== null && active !== null && active > 0 && active < total) parts.push(`${duration(total)} en total`);
  if (recipe.space_id !== null) parts.push("Compartida");
  return parts.join(" · ");
}

const GLYPHS: [RegExp, IconName][] = [
  [/desayun|merienda|brunch/, "sun"],
  [/cena|noche/, "moon"],
  [/suplement/, "bolt"],
];

export function glyphOf(tags: string[]): IconName {
  for (const tag of tags) {
    const found = GLYPHS.find(([pattern]) => pattern.test(fold(tag)));
    if (found) return found[1];
  }
  return "flame";
}

export function hueOf(recipe: { tags: string[]; name: string }): TileHue {
  return toneOf(recipe.tags[0] ?? recipe.name) as TileHue;
}

export function Grid({ recipes, onOpen, muted = false }: { recipes: RecipeSummary[]; onOpen?: (id: string) => void; muted?: boolean }) {
  return (
    <Tiles label="Recetas">
      {recipes.map((recipe) => (
        <Tile
          key={recipe.id}
          title={recipe.name}
          hue={hueOf(recipe)}
          glyph={<Icon name={glyphOf(recipe.tags)} />}
          {...face(recipe)}
          detail={detailOf(recipe)}
          tags={recipe.tags.slice(0, 2)}
          href={`/recipes/receta/${recipe.id}`}
          onOpen={onOpen ? () => onOpen(recipe.id) : undefined}
          muted={muted}
        />
      ))}
    </Tiles>
  );
}

export function Empty({ categories, onNew }: { categories: Category[]; onNew?: () => void }) {
  return (
    <EmptyState
      icon="book"
      hue={7}
      title="Todavía no hay recetas"
      action={onNew ? { label: "Escribir la primera", icon: "plus", onClick: onNew } : undefined}
    >
      <p>
        Una receta lleva sus ingredientes con cantidad, sus pasos con duración y para cuánta gente
        es. Con eso salen solas las macros y el orden de la cocina.
      </p>
      <Inline label="Categorías">
        {categories.map((category) => (
          <Badge key={category.id}>
            <span aria-hidden="true">{category.emoji} </span>
            {category.name}
          </Badge>
        ))}
      </Inline>
    </EmptyState>
  );
}
