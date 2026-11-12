import { BASE } from "./api";

export type SyncState = "saved" | "sending" | "pending";

export interface Op {
  key: string;
  session: string;
  method: "PUT" | "POST";
  path: string;
  body: Record<string, unknown>;
  attempts: number;
}

export type NewOp = Omit<Op, "attempts">;

interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface QueueOptions {
  fetcher?: typeof fetch;
  storage?: KeyValueStorage | null;
  schedule?: (run: () => void, ms: number) => unknown;
  cancel?: (handle: unknown) => void;
}

export type QueueEvent =
  | { type: "rejected"; op: Op; status: number; detail: string }
  | { type: "remapped"; from: string; to: string }
  | { type: "signed-out" };

const STORAGE_KEY = "training.sync";
const PERSON_KEY = "training.sync.person";
const MAX_DELAY_MS = 30_000;

export function retryDelay(attempts: number): number {
  return Math.min(MAX_DELAY_MS, 1000 * 2 ** Math.max(0, attempts - 1));
}

export function isPermanent(status: number): boolean {
  return status >= 400 && status < 500 && status !== 401 && status !== 408 && status !== 429;
}

export class SyncQueue {
  private ops: Op[];
  private sending: string | null = null;
  private timer: unknown = null;
  private version = 0;
  private listeners = new Set<() => void>();
  private eventListeners = new Set<(event: QueueEvent) => void>();
  private readonly fetcher: typeof fetch;
  private readonly storage: KeyValueStorage | null;
  private readonly schedule: (run: () => void, ms: number) => unknown;
  private readonly cancel: (handle: unknown) => void;

  constructor(options: QueueOptions = {}) {
    this.fetcher = options.fetcher ?? ((...args) => fetch(...args));
    this.storage = options.storage === undefined ? safeLocalStorage() : options.storage;
    this.schedule = options.schedule ?? ((run, ms) => setTimeout(run, ms));
    this.cancel = options.cancel ?? ((handle) => clearTimeout(handle as ReturnType<typeof setTimeout>));
    this.ops = this.restore();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  listen(listener: (event: QueueEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  snapshot = (): number => this.version;

  pending(session?: string): Op[] {
    return this.ops.filter((op) => session === undefined || op.session === session);
  }

  hasPending(session?: string): boolean {
    return this.pending(session).length > 0;
  }

  bindPerson(person: string): void {
    try {
      const before = this.storage?.getItem(PERSON_KEY);
      if (before && before !== person && this.ops.length > 0) {
        this.ops = this.sending === null ? [] : this.ops.slice(0, 1);
        this.changed();
      }
      this.storage?.setItem(PERSON_KEY, person);
    } catch {
    }
  }

  forget(session: string): void {
    const before = this.ops.length;
    this.ops = this.ops.filter((op, index) => op.session !== session || (index === 0 && this.sending !== null));
    if (this.ops.length !== before) this.changed();
  }

  stateOf(key: string): SyncState {
    const op = this.ops.find((candidate) => candidate.key === key);
    if (!op) return "saved";
    return op.attempts === 0 ? "sending" : "pending";
  }

  enqueue(op: NewOp): void {
    const waiting = this.ops.findIndex(
      (candidate, index) => candidate.key === op.key && (index > 0 || this.sending === null),
    );
    if (waiting >= 0) {
      this.ops[waiting] = { ...op, attempts: this.ops[waiting]?.attempts ?? 0 };
    } else {
      this.ops.push({ ...op, attempts: 0 });
    }
    this.changed();
    void this.flush();
  }

  async flush(): Promise<void> {
    if (this.sending !== null) return;
    if (this.timer !== null) {
      this.cancel(this.timer);
      this.timer = null;
    }

    for (let op = this.ops[0]; op !== undefined; op = this.ops[0]) {
      this.sending = op.key;
      let status = 0;
      let detail = "";
      let body: unknown = null;
      try {
        const response = await this.fetcher(`${BASE}${op.path}`, {
          method: op.method,
          headers: { accept: "application/json", "content-type": "application/json" },
          body: JSON.stringify(op.body),
        });
        status = response.status;
        body = await response.json().catch(() => null);
        if (!response.ok) detail = describe(body);
      } catch {
        status = 0;
      }
      this.sending = null;

      if (status >= 200 && status < 300) {
        this.ops.shift();
        if (op.key.startsWith("exercise:")) this.remapIfNeeded(op, body);
        this.changed();
        continue;
      }

      if (isPermanent(status)) {
        this.drop(op);
        this.changed();
        this.emit({ type: "rejected", op, status, detail });
        continue;
      }

      const retry = { ...op, attempts: op.attempts + 1 };
      this.ops[0] = retry;
      this.changed();
      if (status === 401) this.emit({ type: "signed-out" });
      this.timer = this.schedule(() => {
        this.timer = null;
        void this.flush();
      }, retryDelay(retry.attempts));
      return;
    }
  }

  private drop(op: Op): void {
    if (op.key.startsWith("start:")) {
      this.ops = this.ops.filter((candidate) => candidate.session !== op.session);
      return;
    }
    const exercise = op.key.startsWith("exercise:") ? op.key.slice("exercise:".length) : null;
    this.ops = this.ops.filter(
      (candidate) =>
        candidate.key !== op.key &&
        (exercise === null ||
          (!candidate.key.startsWith(`set:${exercise}:`) && candidate.key !== `notes:${exercise}`)),
    );
  }

  private remapIfNeeded(op: Op, body: unknown): void {
    const from = op.key.slice("exercise:".length);
    const to = (body as { id?: string } | null)?.id;
    if (!to || to === from) return;
    this.ops = this.ops.map((candidate) =>
      candidate.key.startsWith(`set:${from}:`) || candidate.key === `notes:${from}`
        ? {
            ...candidate,
            key: candidate.key.replace(`set:${from}:`, `set:${to}:`).replace(`notes:${from}`, `notes:${to}`),
            path: candidate.path.replace(`/exercises/${from}/`, `/exercises/${to}/`),
          }
        : candidate,
    );
    this.emit({ type: "remapped", from, to });
  }

  private emit(event: QueueEvent): void {
    for (const listener of this.eventListeners) listener(event);
  }

  private changed(): void {
    this.version += 1;
    try {
      this.storage?.setItem(STORAGE_KEY, JSON.stringify(this.ops));
    } catch {
    }
    for (const listener of this.listeners) listener();
  }

  private restore(): Op[] {
    try {
      const saved = this.storage?.getItem(STORAGE_KEY);
      const parsed: unknown = saved ? JSON.parse(saved) : [];
      return Array.isArray(parsed) ? (parsed as Op[]) : [];
    } catch {
      return [];
    }
  }
}

function describe(body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  return typeof detail === "string" ? detail : "";
}

function safeLocalStorage(): KeyValueStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
