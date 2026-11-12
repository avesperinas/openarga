export function envelopeKey(source: string, widget: string, option?: string | null): string {
  return option ? `${source}/${widget}?${option}` : `${source}/${widget}`;
}

export function widgetUrl(endpoint: string, option?: string | null): string {
  if (!option) return endpoint;
  return `${endpoint}${endpoint.includes("?") ? "&" : "?"}option=${encodeURIComponent(option)}`;
}

export function missing<T extends { source: string; widget: string; option?: string | null }>(
  items: T[],
  have: Record<string, unknown>,
): T[] {
  const asked = new Set<string>();
  return items.filter((item) => {
    const key = envelopeKey(item.source, item.widget, item.option);
    if (key in have || asked.has(key)) return false;
    asked.add(key);
    return true;
  });
}

export function parseEnvelopeKey(key: string): { widget: string; option: string | null } {
  const at = key.indexOf("?");
  return at < 0 ? { widget: key, option: null } : { widget: key.slice(0, at), option: key.slice(at + 1) };
}

export const BATCH = 64;

export const DEFAULT_REFRESH_SECONDS = 300;

export const MAX_REFRESH_SECONDS = 300;

export function stale(
  keys: Iterable<string>,
  refreshOf: (key: string) => number | null | undefined,
  fetched: Record<string, number>,
  now: number,
): string[] {
  return [...new Set(keys)].filter((key) => {
    const at = fetched[key];
    if (at === undefined) return false;
    const seconds = Math.min(refreshOf(key) || DEFAULT_REFRESH_SECONDS, MAX_REFRESH_SECONDS);
    return now - at >= seconds * 1000;
  });
}
