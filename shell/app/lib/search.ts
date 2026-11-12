export interface Found {
  title: string;
  detail?: string;
  href: string;
}

export interface FoundIn {
  app: string;
  name: string;
  results: Found[];
}

export const PER_APP = 8;

export const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase("es");

const inside = (href: unknown): href is string => typeof href === "string" && /^\/(?!\/)/.test(href) && !/\\/.test(href);

const short = (value: unknown, max: number) => (typeof value === "string" ? value.trim().slice(0, max) : "");

export function readFound(body: unknown): Found[] {
  const raw = (body as { results?: unknown } | null)?.results;
  if (!Array.isArray(raw)) return [];
  const found: Found[] = [];
  for (const one of raw) {
    const item = one as { title?: unknown; detail?: unknown; href?: unknown } | null;
    const title = short(item?.title, 160);
    if (!title || !inside(item?.href)) continue;
    const detail = short(item?.detail, 200);
    found.push(detail ? { title, detail, href: item!.href as string } : { title, href: item!.href as string });
    if (found.length === PER_APP) break;
  }
  return found;
}

export function appMatches<T extends { name: string }>(apps: T[], query: string): T[] {
  const wanted = fold(query.trim());
  if (!wanted) return [];
  const hits = apps.filter((app) => fold(app.name).includes(wanted));
  return hits.sort((a, b) => Number(!fold(a.name).startsWith(wanted)) - Number(!fold(b.name).startsWith(wanted)));
}

export async function searchApps(query: string, signal?: AbortSignal): Promise<FoundIn[]> {
  const response = await fetch(`/search?q=${encodeURIComponent(query)}`, {
    credentials: "same-origin",
    headers: { accept: "application/json" },
    signal,
  });
  if (!response.ok) return [];
  const body = (await response.json()) as { groups?: FoundIn[] };
  return Array.isArray(body.groups) ? body.groups : [];
}
