export class Unauthorised extends Error {}

export function problemOf(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const message = String((detail[0] as { msg?: unknown }).msg ?? "");
    return message.replace(/^Value error, /, "") || null;
  }
  return null;
}

export async function answer<T>(url: string, response: Response): Promise<T> {
  if (response.status === 401) throw new Unauthorised("sin sesión");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(problemOf(body) ?? `${url}: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const JSON_ONLY = { accept: "application/json" };

export function signIn(): void {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login?next=${next}`);
}

export interface Api {
  base: string;
  get<T>(path: string): Promise<T>;
  send<T>(path: string, method: string, body?: unknown): Promise<T>;
  raw<T>(url: string): Promise<T>;
  readVersion(): Promise<string>;
  readMe(): Promise<{ user_id: string }>;
}

export function createApi(id: string): Api {
  const base = `/api/${id}`;
  const get = async <T>(path: string) =>
    answer<T>(path, await fetch(`${base}${path}`, { headers: JSON_ONLY }));
  return {
    base,
    get,
    async send<T>(path: string, method: string, body?: unknown) {
      const response = await fetch(`${base}${path}`, {
        method,
        headers: { "content-type": "application/json", ...JSON_ONLY },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      return answer<T>(path, response);
    },
    raw: async <T>(url: string) => answer<T>(url, await fetch(url, { headers: JSON_ONLY })),
    async readVersion() {
      try {
        return (await get<{ version: string }>("/version")).version;
      } catch {
        return "";
      }
    },
    readMe: () => get<{ user_id: string }>("/me"),
  };
}
