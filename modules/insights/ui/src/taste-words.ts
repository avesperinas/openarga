import type { IconName } from "@openarga/ui";

import type { Facet, Family, Hue, PickKind, PickState, Recommendation, Trait } from "./api";
import { intl, t } from "./lang";

export const KINDS: Record<PickKind, { label: string; icon: IconName; hue: Hue }> = {
  book: { get label() { return t("kind.book"); }, icon: "book", hue: 3 },
  podcast: { get label() { return t("kind.podcast"); }, icon: "headphones", hue: 6 },
  episode: { get label() { return t("kind.episode"); }, icon: "headphones", hue: 6 },
  film: { get label() { return t("kind.film"); }, icon: "film", hue: 7 },
  series: { get label() { return t("kind.series"); }, icon: "film", hue: 5 },
  documentary: { get label() { return t("kind.documentary"); }, icon: "film", hue: 2 },
  video: { get label() { return t("kind.video"); }, icon: "play", hue: 4 },
  article: { get label() { return t("kind.article"); }, icon: "note", hue: 1 },
  course: { get label() { return t("kind.course"); }, icon: "target", hue: 8 },
};

export const LISTS: { value: Recommendation["list"]; label: string; icon: IconName }[] = [
  { value: "read", label: "Leer", icon: "book" },
  { value: "watch", label: "Ver", icon: "film" },
  { value: "listen", label: "Escuchar", icon: "headphones" },
];

export const STATES: Record<PickState, string> = {
  get new() { return t("state.new"); },
  get saved() { return t("state.saved"); },
  get doing() { return t("state.doing"); },
  get done() { return t("state.done"); },
  get dismissed() { return t("state.dismissed"); },
};

export function nextState(state: PickState): PickState {
  if (state === "saved" || state === "new") return "doing";
  if (state === "doing") return "done";
  return "saved";
}

export const FACETS: Record<Facet, { label: string; icon: IconName }> = {
  topic: { get label() { return t("facet.topic"); }, icon: "spark" },
  genre: { get label() { return t("facet.genre"); }, icon: "bookmark" },
  format: { get label() { return t("facet.format"); }, icon: "layers" },
  creator: { get label() { return t("facet.creator"); }, icon: "people" },
  work: { get label() { return t("facet.work"); }, icon: "heart" },
  style: { get label() { return t("facet.style"); }, icon: "note" },
  avoid: { get label() { return t("facet.avoid"); }, icon: "eye-off" },
  context: { get label() { return t("facet.context"); }, icon: "target" },
  language: { get label() { return t("facet.language"); }, icon: "globe" },
};

export const FACET_ORDER: Facet[] = ["topic", "genre", "format", "creator", "work", "style", "context", "language", "avoid"];

export const SOURCES: Record<Trait["source"], string> = {
  get said() { return t("source.said"); },
  get answered() { return t("source.answered"); },
  get seen() { return t("source.seen"); },
  get rated() { return t("source.rated"); },
};

export const STANCES: { value: string; label: string }[] = [
  { value: "2", get label() { return t("stance.2"); } },
  { value: "1", get label() { return t("stance.1"); } },
  { value: "-1", get label() { return t("stance.-1"); } },
  { value: "-2", get label() { return t("stance.-2"); } },
];

export const WEIGHTS = [
  { value: "0", get label() { return t("weight.0"); } },
  { value: "1", get label() { return t("weight.1"); } },
  { value: "2", get label() { return t("weight.2"); } },
  { value: "3", get label() { return t("weight.3"); } },
];

export const LANGUAGES: { value: string; label: string }[] = [
  { value: "none", get label() { return t("language.none"); } },
  { value: "de", get label() { return t("language.de"); } },
  { value: "en", get label() { return t("language.en"); } },
  { value: "fr", get label() { return t("language.fr"); } },
  { value: "it", get label() { return t("language.it"); } },
];

const GLYPHS = new Set<string>([
  "landmark", "globe", "atom", "chip", "wallet", "book", "mountain", "image", "spark", "compass", "music", "food",
  "heart", "flame", "graph", "layers", "plane", "target", "bolt", "people", "castle", "film", "headphones", "lightbulb",
]);

export const glyphOf = (family: Pick<Family, "glyph"> | undefined): IconName =>
  (family && GLYPHS.has(family.glyph) ? family.glyph : "spark") as IconName;

const FALLBACK: Family = { key: "", name: "", hue: 8, glyph: "spark", themes: "", weight: 1, outside: false };

export const familyOf = (families: Family[], key: string): Family =>
  families.find((one) => one.key === key) ?? { ...FALLBACK, key, name: key };

export const longDay = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(intl(), { weekday: "long", day: "numeric", month: "long" });

export const shortDay = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString(intl(), { day: "numeric", month: "short" });

export function detailOf(pick: Recommendation): string {
  return [pick.creators.slice(0, 2).join(", "), pick.year ? String(pick.year) : null, pick.length]
    .filter(Boolean)
    .join(" · ");
}

export const ORIGINS: Record<"daily" | "surprise" | "branch", string> = {
  get daily() { return t("origin.daily"); },
  get surprise() { return t("origin.surprise"); },
  get branch() { return t("origin.branch"); },
};
