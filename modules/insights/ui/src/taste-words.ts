import type { IconName } from "@openarga/ui";

import type { Facet, Family, Hue, PickKind, PickState, Recommendation, Trait } from "./api";

export const KINDS: Record<PickKind, { label: string; icon: IconName; hue: Hue }> = {
  book: { label: "Libro", icon: "book", hue: 3 },
  podcast: { label: "Podcast", icon: "headphones", hue: 6 },
  episode: { label: "Episodio", icon: "headphones", hue: 6 },
  film: { label: "Película", icon: "film", hue: 7 },
  series: { label: "Serie", icon: "film", hue: 5 },
  documentary: { label: "Documental", icon: "film", hue: 2 },
  video: { label: "Vídeo", icon: "play", hue: 4 },
  article: { label: "Artículo", icon: "note", hue: 1 },
  course: { label: "Curso", icon: "target", hue: 8 },
};

export const LISTS: { value: Recommendation["list"]; label: string; icon: IconName }[] = [
  { value: "read", label: "Leer", icon: "book" },
  { value: "watch", label: "Ver", icon: "film" },
  { value: "listen", label: "Escuchar", icon: "headphones" },
];

export const STATES: Record<PickState, string> = {
  new: "Sin abrir",
  saved: "Pendiente",
  doing: "En curso",
  done: "Hecho",
  dismissed: "Descartado",
};

export function nextState(state: PickState): PickState {
  if (state === "saved" || state === "new") return "doing";
  if (state === "doing") return "done";
  return "saved";
}

export const FACETS: Record<Facet, { label: string; icon: IconName }> = {
  topic: { label: "Temas", icon: "spark" },
  genre: { label: "Géneros", icon: "bookmark" },
  format: { label: "Formatos", icon: "layers" },
  creator: { label: "Autores y creadores", icon: "people" },
  work: { label: "Obras que te marcaron", icon: "heart" },
  style: { label: "Cómo te gusta que te lo cuenten", icon: "note" },
  avoid: { label: "De lo que no quieres que te hable", icon: "eye-off" },
  context: { label: "Lo que vives ahora", icon: "target" },
  language: { label: "Idiomas", icon: "globe" },
};

export const FACET_ORDER: Facet[] = ["topic", "genre", "format", "creator", "work", "style", "context", "language", "avoid"];

export const SOURCES: Record<Trait["source"], string> = {
  said: "Lo dijiste",
  answered: "Lo contestaste",
  seen: "Lo vio en tus datos",
  rated: "Por lo que valoraste",
};

export const STANCES: { value: string; label: string }[] = [
  { value: "2", label: "Me encanta" },
  { value: "1", label: "Me gusta" },
  { value: "-1", label: "No me va" },
  { value: "-2", label: "No quiero" },
];

export const WEIGHTS = [
  { value: "0", label: "Nada" },
  { value: "1", label: "Algo" },
  { value: "2", label: "Bastante" },
  { value: "3", label: "Mucho" },
];

export const LANGUAGES: { value: string; label: string }[] = [
  { value: "none", label: "Ninguno" },
  { value: "de", label: "Alemán" },
  { value: "en", label: "Inglés" },
  { value: "fr", label: "Francés" },
  { value: "it", label: "Italiano" },
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
  new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" });

export const shortDay = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "short" });

export function detailOf(pick: Recommendation): string {
  return [pick.creators.slice(0, 2).join(", "), pick.year ? String(pick.year) : null, pick.length]
    .filter(Boolean)
    .join(" · ");
}

export const ORIGINS: Record<"daily" | "surprise" | "branch", string> = {
  daily: "del día",
  surprise: "sorpresa",
  branch: "para saber más",
};
