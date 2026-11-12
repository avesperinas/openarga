import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import { createApi, Unauthorised } from "./api";
import { bindPerson, forgetSeen, loadSeen } from "./persist";
import { reset, seed } from "./resource";

const HYDRATE_MS = 50;
const RELOADED = "arga-app-reloaded";
const RELOAD_EVERY_MS = 60_000;

export interface MountOptions {
  onPerson?: (person: string) => void | Promise<void>;
  api?: string;
}

export async function mountApp(id: string, app: ReactNode, options: MountOptions = {}): Promise<void> {
  const seen = loadSeen(id).then(seed);
  await Promise.race([seen, new Promise((resolve) => setTimeout(resolve, HYDRATE_MS))]);

  createRoot(document.getElementById("root")!).render(<StrictMode>{app}</StrictMode>);

  void seen.then(() => whoIs(options.api ?? id, options.onPerson));
  stayOnOneVersion(id);
  register(id);
}

async function whoIs(id: string, onPerson?: MountOptions["onPerson"]): Promise<void> {
  try {
    const { user_id } = await createApi(id).readMe();
    if (bindPerson(user_id)) {
      await reset();
      bindPerson(user_id);
    }
    await onPerson?.(user_id);
  } catch (error) {
    if (error instanceof Unauthorised) await forgetSeen();
  }
}

function stayOnOneVersion(id: string): void {
  window.addEventListener("vite:preloadError", () => {
    try {
      const last = Number(sessionStorage.getItem(RELOADED) ?? 0);
      if (Date.now() - last < RELOAD_EVERY_MS) return;
      sessionStorage.setItem(RELOADED, String(Date.now()));
    } catch {
      return;
    }
    const switched =
      "serviceWorker" in navigator
        ? new Promise<void>((resolve) => {
            navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), { once: true });
            void navigator.serviceWorker
              .getRegistration(`/${id}/`)
              .then((registration) => registration?.update())
              .catch(() => undefined);
          })
        : new Promise<void>(() => undefined);
    void Promise.race([switched, new Promise((resolve) => setTimeout(resolve, 3000))]).then(() =>
      window.location.reload(),
    );
  });
}

function register(id: string): void {
  if (!("serviceWorker" in navigator) || !(import.meta as { env?: { PROD?: boolean } }).env?.PROD) return;
  const start = () => void navigator.serviceWorker.register(`/${id}/sw.js`, { scope: `/${id}/` }).catch(() => undefined);
  if ("requestIdleCallback" in window) window.requestIdleCallback(start);
  else setTimeout(start, 1000);
}
