const FROM = "áàâäãéèêëíìîïóòôöõúùûüñç";
const TO = "aaaaaeeeeiiiiooooouuuunc";

export function fold(value: string | null | undefined): string {
  return Array.from((value ?? "").toLowerCase(), (char) => {
    const at = FROM.indexOf(char);
    return at < 0 ? char : TO[at]!;
  }).join("");
}

export function closeness(query: string, ...names: (string | null | undefined)[]): number | null {
  const wanted = fold(query.trim());
  const folded = names.filter(Boolean).map(fold);
  if (!wanted) return 0;
  if (folded.some((one) => one === wanted)) return 0;
  if (folded.some((one) => one.startsWith(wanted))) return 1;
  if (folded.some((one) => ` ${one}`.includes(` ${wanted}`))) return 2;
  if (folded.some((one) => one.includes(wanted))) return 3;
  return null;
}

export function ranked<T>(items: T[], query: string, names: (item: T) => (string | null | undefined)[], label: (item: T) => string): T[] {
  return items
    .map((item) => ({ item, score: closeness(query, ...names(item)) }))
    .filter((one): one is { item: T; score: number } => one.score !== null)
    .sort((a, b) => a.score - b.score || label(a.item).localeCompare(label(b.item), "es"))
    .map(({ item }) => item);
}
