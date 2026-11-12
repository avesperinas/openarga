import { useCallback, useEffect, useSyncExternalStore } from "react";

import { answer } from "./api";

export interface Pending {
  key?: number;
  person: string | null;
  method: string;
  url: string;
  body: unknown;
  what: string;
  at: string;
}

export interface Refused extends Pending {
  problem: string;
}

export interface Store {
  all(): Promise<Pending[]>;
  add(item: Pending): Promise<void>;
  remove(key: number): Promise<void>;
  refused(): Promise<Refused[]>;
  refuse(item: Refused): Promise<void>;
  forget(key: number): Promise<void>;
  clear(): Promise<void>;
}

export class Queued extends Error {
  constructor() {
    super("Sin conexión: se guarda y se envía al volver la red.");
  }
}

export class NeedsNetwork extends Error {
  constructor() {
    super("Sin conexión: esto necesita red.");
  }
}

export function repeatable(method: string, body: unknown): boolean {
  if (method === "PUT" || method === "DELETE") return true;
  if (method !== "POST" || typeof body !== "object" || body === null) return false;
  const withId = (one: unknown) => typeof one === "object" && one !== null && "id" in one;
  if (Array.isArray(body)) return body.length > 0 && body.every(withId);
  const items = (body as { items?: unknown }).items;
  if (Array.isArray(items)) return items.length > 0 && items.every(withId);
  return withId(body);
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export function browserStore(app: string): Store {
  const open = (): Promise<IDBDatabase> =>
    new Promise((resolve, reject) => {
      const req = indexedDB.open(`${app}-offline`, 2);
      req.onupgradeneeded = () => {
        for (const name of ["queue", "refused"]) {
          if (!req.result.objectStoreNames.contains(name)) {
            req.result.createObjectStore(name, { keyPath: "key", autoIncrement: true });
          }
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  const on = async <T>(name: string, mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) => {
    const db = await open();
    try {
      return await request(run(db.transaction(name, mode).objectStore(name)));
    } finally {
      db.close();
    }
  };
  return {
    all: () => on("queue", "readonly", (s) => s.getAll() as IDBRequest<Pending[]>),
    add: async (item) => void (await on("queue", "readwrite", (s) => s.add(item))),
    remove: async (key) => void (await on("queue", "readwrite", (s) => s.delete(key))),
    refused: () => on("refused", "readonly", (s) => s.getAll() as IDBRequest<Refused[]>),
    refuse: async (item) => {
      const fresh: Partial<Refused> = { ...item };
      delete fresh.key;
      await on("refused", "readwrite", (s) => s.add(fresh));
    },
    forget: async (key) => void (await on("refused", "readwrite", (s) => s.delete(key))),
    clear: async () => {
      await on("queue", "readwrite", (s) => s.clear());
      await on("refused", "readwrite", (s) => s.clear());
    },
  };
}

export function memoryStore(): Store {
  let next = 1;
  let queue: Pending[] = [];
  let refused: Refused[] = [];
  return {
    all: async () => [...queue],
    add: async (item) => void queue.push({ ...item, key: next++ }),
    remove: async (key) => void (queue = queue.filter((one) => one.key !== key)),
    refused: async () => [...refused],
    refuse: async (item) => void refused.push({ ...item, key: next++ }),
    forget: async (key) => void (refused = refused.filter((one) => one.key !== key)),
    clear: async () => {
      queue = [];
      refused = [];
    },
  };
}

export interface Flushed {
  sent: number;
  signedOut: boolean;
  offline: boolean;
}

export interface QueueState {
  pending: number;
  refused: Refused[];
  signedOut: boolean;
}

export interface SendOptions {
  what?: string;
  repeatable?: boolean;
}

export interface OfflineQueue {
  send<T>(url: string, method: string, body?: unknown, options?: SendOptions): Promise<T>;
  flush(now?: boolean): Promise<Flushed>;
  bindPerson(person: string): Promise<void>;
  retry(key: number): Promise<void>;
  dismiss(key: number): Promise<void>;
  subscribe(listener: () => void): () => void;
  state(): QueueState;
  onSent(listener: () => void): () => void;
}

export interface QueueOptions {
  app: string;
  store?: Store;
  fetcher?: typeof fetch;
}

const BACKOFF_MS = [0, 2_000, 5_000, 15_000, 30_000];

export function createOfflineQueue({ app, store, fetcher }: QueueOptions): OfflineQueue {
  const kept = store ?? (typeof indexedDB === "undefined" ? memoryStore() : browserStore(app));
  const call = (url: string, method: string, body: unknown) =>
    (fetcher ?? fetch)(url, {
      method,
      headers: { "content-type": "application/json", accept: "application/json" },
      body: body === undefined || body === null ? undefined : JSON.stringify(body),
    });
  const PERSON = `${app}-offline-person`;
  let person: string | null = null;
  try {
    person = localStorage.getItem(PERSON);
  } catch {
  }
  let current: QueueState = { pending: 0, refused: [], signedOut: false };
  const listeners = new Set<() => void>();
  const sentListeners = new Set<() => void>();
  let failures = 0;
  let retryAt = 0;
  let running: Promise<Flushed> | null = null;

  async function load() {
    const mine = (one: Pending) => one.person === person;
    const [queue, refused] = await Promise.all([kept.all(), kept.refused()]);
    current = { ...current, pending: queue.filter(mine).length, refused: refused.filter(mine) };
    for (const listener of listeners) listener();
  }

  async function same(result: Flushed): Promise<boolean> {
    let response: Response;
    try {
      response = await (fetcher ?? fetch)(`/api/${app}/me`, { headers: { accept: "application/json" } });
    } catch {
      result.offline = true;
      return false;
    }
    if (response.status === 401) {
      result.signedOut = true;
      return false;
    }
    if (!response.ok) {
      result.offline = true;
      return false;
    }
    const { user_id } = (await response.json()) as { user_id: string };
    if (user_id === person) return true;
    await bind(user_id);
    return false;
  }

  async function bind(id: string) {
    if (person === id) return;
    if (person !== null) await kept.clear();
    person = id;
    try {
      localStorage.setItem(PERSON, id);
    } catch {
    }
  }

  async function pass(): Promise<Flushed> {
    const result: Flushed = { sent: 0, signedOut: false, offline: false };
    const waiting = (await kept.all()).filter((one) => one.person === person);
    if (waiting.length === 0) return result;
    if (!(await same(result))) {
      current = { ...current, signedOut: result.signedOut };
      await load();
      return result;
    }
    for (const item of waiting) {
      if (item.person !== person) continue;
      let response: Response;
      try {
        response = await call(item.url, item.method, item.body);
      } catch {
        result.offline = true;
        break;
      }
      if (response.status === 401) {
        result.signedOut = true;
        break;
      }
      if (response.status >= 500) {
        result.offline = true;
        break;
      }
      if (!response.ok) {
        let problem = `${response.status}`;
        try {
          await answer(item.url, response);
        } catch (error) {
          problem = error instanceof Error ? error.message : problem;
        }
        await kept.refuse({ ...item, problem });
      } else {
        result.sent += 1;
      }
      await kept.remove(item.key!);
    }
    failures = result.offline ? failures + 1 : 0;
    retryAt = Date.now() + BACKOFF_MS[Math.min(failures, BACKOFF_MS.length - 1)]!;
    current = { ...current, signedOut: result.signedOut };
    await load();
    if (result.sent > 0) for (const listener of sentListeners) listener();
    return result;
  }

  function flush(): Promise<Flushed> {
    if (running) return running;
    const locks = (navigator as { locks?: LockManager }).locks;
    running = (locks ? (locks.request(`${app}-queue`, pass) as unknown as Promise<Flushed>) : pass()).finally(() => {
      running = null;
    });
    return running;
  }

  async function queue(url: string, method: string, body: unknown, what: string): Promise<never> {
    if (person === null) throw new NeedsNetwork();
    await kept.add({ person, method, url, body: body ?? null, what, at: new Date().toISOString() });
    await load();
    throw new Queued();
  }

  void load().catch(() => undefined);

  return {
    async send<T>(url: string, method: string, body?: unknown, options: SendOptions = {}) {
      const canWait = options.repeatable ?? repeatable(method, body);
      const what = options.what ?? "un cambio";
      await load();
      if (current.pending > 0) {
        await flush();
        if (current.pending > 0) {
          if (!canWait) throw new NeedsNetwork();
          return queue(url, method, body, what);
        }
      }
      let response: Response;
      try {
        response = await call(url, method, body);
      } catch {
        if (!canWait) throw new NeedsNetwork();
        return queue(url, method, body, what);
      }
      return answer<T>(url, response);
    },
    flush: (now = false) =>
      !now && Date.now() < retryAt ? Promise.resolve({ sent: 0, signedOut: false, offline: true }) : flush(),
    async bindPerson(id) {
      await bind(id);
      await load();
    },
    async retry(key) {
      const found = current.refused.find((one) => one.key === key);
      if (!found) return;
      await kept.forget(key);
      const item: Partial<Refused> = { ...found };
      delete item.key;
      delete item.problem;
      await kept.add(item as Pending);
      await load();
      await flush();
    },
    async dismiss(key) {
      await kept.forget(key);
      await load();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    state: () => current,
    onSent(listener) {
      sentListeners.add(listener);
      return () => sentListeners.delete(listener);
    },
  };
}

const EVERY_MS = 30_000;

export function useOfflineQueue(queue: OfflineQueue): QueueState & {
  retry: (key: number) => Promise<void>;
  dismiss: (key: number) => Promise<void>;
} {
  const state = useSyncExternalStore(queue.subscribe, queue.state, queue.state);
  const flush = useCallback((now = false) => void queue.flush(now).catch(() => undefined), [queue]);
  useEffect(() => {
    flush(true);
    const online = () => flush(true);
    const visible = () => document.visibilityState === "visible" && flush(true);
    window.addEventListener("online", online);
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.removeEventListener("online", online);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [flush]);
  useEffect(() => {
    if (state.pending === 0) return;
    const timer = setInterval(() => flush(), EVERY_MS);
    return () => clearInterval(timer);
  }, [flush, state.pending]);
  return { ...state, retry: queue.retry, dismiss: queue.dismiss };
}
