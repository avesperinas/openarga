const FROM = "\u00e1\u00e0\u00e2\u00e4\u00e3\u00e9\u00e8\u00ea\u00eb\u00ed\u00ec\u00ee\u00ef\u00f3\u00f2\u00f4\u00f6\u00f5\u00fa\u00f9\u00fb\u00fc\u00f1\u00e7";
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
    .sort((a, b) => a.score - b.score || label(a.item).localeCompare(label(b.item)))
    .map(({ item }) => item);
}
