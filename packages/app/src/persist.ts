interface Seen {
  person: string | null;
  entries: Record<string, unknown>;
}

const STORE = "seen";
const RECORD = "app";
const WRITE_AFTER_MS = 300;

let app: string | null = null;
let current: Seen = { person: null, entries: {} };
let timer: ReturnType<typeof setTimeout> | null = null;

function open(id: string): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    const request = indexedDB.open(`arga-app-${id}`, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });
}

async function save(): Promise<void> {
  if (!app) return;
  const db = await open(app);
  if (!db) return;
  await new Promise<void>((resolve) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(current, RECORD);
    tx.oncomplete = tx.onerror = tx.onabort = () => {
      db.close();
      resolve();
    };
  });
}

function later(): void {
  if (!app) return;
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = null;
    void save();
  }, WRITE_AFTER_MS);
}

export async function loadSeen(id: string): Promise<Record<string, unknown>> {
  app = id;
  const db = await open(id);
  if (!db) return {};
  const found = await new Promise<Seen | undefined>((resolve) => {
    const request = db.transaction(STORE).objectStore(STORE).get(RECORD);
    request.onsuccess = () => resolve(request.result as Seen | undefined);
    request.onerror = () => resolve(undefined);
  });
  db.close();
  if (found) current = { person: found.person, entries: { ...found.entries, ...current.entries } };
  return found?.entries ?? {};
}

export function keep(key: string, data: unknown): void {
  current.entries[key] = data;
  later();
}

export function bindPerson(person: string): boolean {
  const other = current.person !== null && current.person !== person;
  current = { person, entries: other ? {} : current.entries };
  later();
  return other;
}

export function forgetSeen(): Promise<void> {
  current = { person: null, entries: {} };
  if (timer) clearTimeout(timer);
  timer = null;
  return save();
}
