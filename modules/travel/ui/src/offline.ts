import type { OfflineQueue } from "@openarga/app/offline";

export { NeedsNetwork, Queued } from "@openarga/app/offline";

let told: string | null = null;

export async function register(person: string): Promise<void> {
  told = person;
  if (!("serviceWorker" in navigator)) return;
  try {
    const registration = await navigator.serviceWorker.register("/travel/sw.js", { scope: "/travel/" });
    const worker = registration.active ?? registration.waiting ?? registration.installing;
    const tell = (target: ServiceWorker | null | undefined) => target?.postMessage({ type: "person", id: person });
    tell(worker);
    navigator.serviceWorker.ready.then((ready) => tell(ready.active)).catch(() => undefined);
  } catch {
  }
}

export async function controlled(timeout = 20_000): Promise<boolean> {
  if (!("serviceWorker" in navigator)) return false;
  const container = navigator.serviceWorker;
  if (!container.controller) {
    await new Promise<void>((resolve) => {
      const done = () => {
        container.removeEventListener("controllerchange", done);
        clearTimeout(timer);
        resolve();
      };
      const timer = setTimeout(done, timeout);
      container.addEventListener("controllerchange", done);
    });
  }
  const controller = container.controller;
  if (!controller) return false;
  if (told) controller.postMessage({ type: "person", id: told });
  return true;
}

export interface OldPending {
  key?: number;
  method: string;
  path?: string;
  url?: string;
  person?: string | null;
  body: unknown;
  what: string;
  at: string;
}

export function adopt(item: OldPending, person: string): OldPending {
  if (item.url) return item;
  const { path, ...rest } = item;
  return { ...rest, url: `/api/travel${path ?? ""}`, person };
}

export async function adoptOldQueue(person: string, queue: OfflineQueue): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("travel-offline");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    try {
      if (!db.objectStoreNames.contains("queue")) return;
      const store = db.transaction("queue", "readwrite").objectStore("queue");
      const items = await new Promise<OldPending[]>((resolve, reject) => {
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result as OldPending[]);
        request.onerror = () => reject(request.error);
      });
      const old = items.filter((one) => !one.url);
      for (const item of old) store.put(adopt(item, person));
      if (old.length) await queue.bindPerson(person);
    } finally {
      db.close();
    }
  } catch {
  }
}
