/* global self, caches, fetch, URL, setTimeout, clearTimeout, __APP__ */
const APP = __APP__;
const PREFIX = `${APP.id}-app-`;
const CURRENT = `${PREFIX}2-`;
const CACHE = `${CURRENT}${APP.version}`;
const PAGE_WAIT_MS = 4000;

function pick(url, mode, origin) {
  if (url.origin !== origin) return "pass";
  if (!url.pathname.startsWith(APP.root) && url.pathname !== APP.root.slice(0, -1)) return "pass";
  if (url.pathname === `${APP.root}sw.js`) return "pass";
  if (mode === "navigate") return "page";
  if (url.pathname.startsWith(`${APP.root}assets/`)) return "asset";
  return "file";
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(APP.precache))
      .then(() => self.skipWaiting()),
  );
});

function stale(names) {
  const old = names.filter((name) => name.startsWith(PREFIX) && name !== CACHE);
  return { old, servedOld: old.some((name) => !name.startsWith(CURRENT)) };
}

self.addEventListener("activate", (event) => {
  const activated = caches.keys().then(async (names) => {
    const { old, servedOld } = stale(names);
    await Promise.all(old.map((name) => caches.delete(name)));
    await self.clients.claim();
    return servedOld;
  });
  event.waitUntil(activated);
  void activated.then(async (servedOld) => {
    if (!servedOld) return;
    const windows = await self.clients.matchAll({ type: "window" });
    await Promise.all(windows.map((client) => client.navigate(client.url).catch(() => undefined)));
  });
});

function worthKeeping(response) {
  return (
    response.ok &&
    response.type === "basic" &&
    !response.redirected &&
    !(response.headers.get("content-type") ?? "").includes("text/html")
  );
}

async function page(request) {
  const kept = () => caches.open(CACHE).then((cache) => cache.match(APP.root));
  const network = fetch(request);
  let timer;
  const late = new Promise((resolve) => {
    timer = setTimeout(() => resolve(null), PAGE_WAIT_MS);
  });
  try {
    const response = await Promise.race([network, late]);
    if (response && response.status < 500) return response;
    const fallback = await kept();
    if (fallback) return fallback;
    return response ?? (await network);
  } catch (error) {
    const fallback = await kept();
    if (fallback) return fallback;
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function asset(request) {
  const cache = await caches.open(CACHE);
  const kept = await cache.match(request);
  if (kept) return kept;
  const response = await fetch(request);
  if (worthKeeping(response)) await cache.put(request, response.clone());
  return response;
}

async function file(request) {
  const cache = await caches.open(CACHE);
  return (await cache.match(request, { ignoreSearch: true })) ?? fetch(request);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const kind = pick(new URL(request.url), request.mode, self.location.origin);
  if (kind === "page") event.respondWith(page(request));
  else if (kind === "asset") event.respondWith(asset(request));
  else if (kind === "file") event.respondWith(file(request));
});
