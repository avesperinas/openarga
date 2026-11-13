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
  type Translate,
  useT,
} from "@openarga/ui";
import { useMemo, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Category, type RecipeSummary, readArchived, readCategories, readRecipes } from "./api";
import { categoryName } from "./categories";
import { ScreenHeader } from "./Header";

export function RecipesScreen({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const t = useT();
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
      <ScreenHeader title={t("tabs.recipes")} />
      <OfflineNotice />
      {found.loading && <Skeleton label={t("recipes.loading")} />}
      {!recipes && found.error && (
        <ErrorState title={t("recipes.read_failed")} detail={found.error.message} onRetry={found.refresh} />
      )}
      {recipes && recipes.length === 0 && <Empty categories={categories} onNew={onNew} />}
      {recipes && recipes.length > 0 && (
        <>
          <SearchField label={t("recipes.search")} placeholder={t("recipes.search_placeholder")} value={query} onChange={setQuery} />
          {tags.length > 1 && (
            <ChoiceChips
              label={t("recipes.tag")}
              value={tag}
              onChange={setTag}
              options={[{ value: ALL, label: t("recipes.all") }, ...tags.map((one) => ({ value: one, label: one }))]}
            />
          )}
          {shown.length > 0 ? (
            <Grid recipes={shown} onOpen={onOpen} />
          ) : (
            <EmptyState icon="search" title={t("recipes.none_like_that")}>
              {t("recipes.try_other")}
            </EmptyState>
          )}
        </>
      )}
      {archived.length > 0 && (
        <Collapsible
          title={t("recipes.archived", { count: archived.length })}
          subtitle={t("recipes.archived_hint")}
        >
          <Grid recipes={archived} onOpen={onOpen} muted />
        </Collapsible>
      )}
      {recipes && <CreateButton label={t("recipes.new")} onClick={onNew} />}
      <AppVersion />
    </Screen>
  );
}

const ALL = "";

export function tagsByUse(recipes: RecipeSummary[]): string[] {
  const uses = new Map<string, number>();
  for (const recipe of recipes) for (const tag of recipe.tags) uses.set(tag, (uses.get(tag) ?? 0) + 1);
  return [...uses].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([tag]) => tag);
}

const fold = (text: string) =>
  text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase();

export function filtered(recipes: RecipeSummary[], query: string, tag: string): RecipeSummary[] {
  const wanted = fold(query.trim());
  return recipes.filter(
    (recipe) =>
      (tag === ALL || recipe.tags.includes(tag)) &&
      (!wanted || fold(recipe.name).includes(wanted) || recipe.tags.some((one) => fold(one).includes(wanted))),
  );
}

export function face(
  recipe: Pick<RecipeSummary, "total_minutes" | "active_minutes">,
  t: Translate,
): { figure?: string; caption?: string } {
  const { total_minutes: total, active_minutes: active } = recipe;
  if (total === null || active === null) return {};
  if (total === 0) return { figure: t("face.instant") };
  if (active === 0) return { figure: t("face.no_work"), caption: t("face.in_all", { time: duration(total) }) };
  if (active === total) return { figure: duration(total), caption: t("face.in_all_short") };
  return { figure: duration(active), caption: t("face.you_there") };
}

export function detailOf(recipe: RecipeSummary, t: Translate): string {
  const parts = [t(recipe.servings === 1 ? "detail.for.one" : "detail.for.other", { count: recipe.servings })];
  const { total_minutes: total, active_minutes: active } = recipe;
  if (total !== null && active !== null && active > 0 && active < total) parts.push(t("face.in_all", { time: duration(total) }));
  if (recipe.space_id !== null) parts.push(t("share.shared"));
  return parts.join(" · ");
}

const GLYPHS: [RegExp, IconName][] = [
  [/breakfast|brunch|snack|desayun|merienda/, "sun"],
  [/dinner|night|cena|noche/, "moon"],
  [/supplement|suplement/, "bolt"],
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
  const t = useT();
  return (
    <Tiles label={t("recipes.tiles")}>
      {recipes.map((recipe) => (
        <Tile
          key={recipe.id}
          title={recipe.name}
          hue={hueOf(recipe)}
          glyph={<Icon name={glyphOf(recipe.tags)} />}
          {...face(recipe, t)}
          detail={detailOf(recipe, t)}
          tags={recipe.tags.slice(0, 2)}
          href={`/recipes/recipe/${recipe.id}`}
          onOpen={onOpen ? () => onOpen(recipe.id) : undefined}
          muted={muted}
        />
      ))}
    </Tiles>
  );
}

export function Empty({ categories, onNew }: { categories: Category[]; onNew?: () => void }) {
  const t = useT();
  return (
    <EmptyState
      icon="book"
      hue={7}
      title={t("recipes.empty")}
      action={onNew ? { label: t("recipes.write_first"), icon: "plus", onClick: onNew } : undefined}
    >
      <p>{t("recipes.empty_detail")}</p>
      <Inline label={t("recipes.categories")}>
        {categories.map((category) => (
          <Badge key={category.id}>
            <span aria-hidden="true">{category.emoji} </span>
            {categoryName(t, category.id, category.name)}
          </Badge>
        ))}
      </Inline>
    </EmptyState>
  );
}
