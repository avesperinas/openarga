export const byName = new Intl.Collator("es", { numeric: true, sensitivity: "base" }).compare;

export function splitCode(title: string): { prefix: string; number: string; name: string } | null {
  const match = /^(?:([A-ZÄÖÜ]{1,4})\s+)?(\d+(?:\.\d+)*)\.?\s+(?:[-–—:·]\s+)?(\S.*)$/u.exec(title.trim());
  if (!match) return null;
  return { prefix: match[1] ?? "", number: match[2]!, name: match[3]! };
}

export function codeColumn(titles: string[]): (string | null)[] {
  const codes = titles.map(splitCode);
  const numbered = codes.filter((code) => code !== null);
  const shared = numbered.length > 0 && numbered.every((code) => code.prefix === numbered[0]!.prefix);
  return codes.map((code) => (code ? (shared || !code.prefix ? code.number : `${code.prefix} ${code.number}`) : null));
}

export function neighbours<T extends { id: string; title: string; folder: string; session_id: string | null }>(
  notes: T[],
  current: { id: string; folder: string },
): { previous: T | null; next: T | null } {
  const same = notes.filter((note) => note.folder === current.folder && !note.session_id).sort((a, b) => byName(a.title, b.title));
  const at = same.findIndex((note) => note.id === current.id);
  if (at < 0) return { previous: null, next: null };
  return { previous: same[at - 1] ?? null, next: same[at + 1] ?? null };
}

export function reading(body: string): { words: number; minutes: number } {
  const text = body.replace(/```[\s\S]*?```/g, " ").replace(/[#>*_`|~=-]+/g, " ");
  const words = text.split(/\s+/).filter((word) => /[\p{L}\p{N}]/u.test(word)).length;
  return { words, minutes: Math.max(1, Math.round(words / 220)) };
}

export function resolver(notes: { id: string; title: string }[]): (target: string) => string | null {
  const key = (text: string) => text.split("/").pop()!.replace(/\.md$/i, "").normalize("NFC").trim().toLocaleLowerCase("es");
  const ids = new Map(notes.map((note) => [key(note.title), note.id]));
  return (target) => ids.get(key(target)) ?? null;
}
