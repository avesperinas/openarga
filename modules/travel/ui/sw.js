/* global self, caches, fetch, Response, URL */
const VERSION = "__VERSION__";
const APP = `travel-app-${VERSION}`;
const TILES = "travel-tiles";
const DATA_PREFIX = "travel-data-";
let person = null;

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(APP);
      const list = await (await fetch("/travel/precache.json", { cache: "no-cache" })).json();
      await cache.addAll(list);
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) {
        if (name.startsWith("travel-app-") && name !== APP) await caches.delete(name);
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  const message = event.data || {};
  if (message.type === "person") {
    person = message.id;
    event.waitUntil(
      (async () => {
        for (const name of await caches.keys()) {
          if (name.startsWith(DATA_PREFIX) && name !== DATA_PREFIX + person) await caches.delete(name);
        }
      })(),
    );
  }
});

async function dataCache() {
  if (person) return DATA_PREFIX + person;
  const found = (await caches.keys()).find((name) => name.startsWith(DATA_PREFIX));
  return found || null;
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok && cacheName) {
      const cache = await caches.open(cacheName);
      await cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = cacheName ? await (await caches.open(cacheName)).match(request) : undefined;
    if (cached) return cached;
    throw error;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (
    url.pathname.startsWith("/api/travel/tiles/") ||
    url.pathname.startsWith("/travel/map/fonts/") ||
    url.pathname.startsWith("/travel/geo/")
  ) {
    event.respondWith(cacheFirst(request, TILES));
    return;
  }
  if (url.pathname.startsWith("/api/travel/")) {
    event.respondWith((async () => networkFirst(request, await dataCache()))());
    return;
  }
  if (request.mode === "navigate" && url.pathname.startsWith("/travel")) {
    event.respondWith(
      (async () => {
        try {
          return await fetch(request);
        } catch {
          return (await caches.match("/travel/", { cacheName: APP })) || Response.error();
        }
      })(),
    );
    return;
  }
  if (url.pathname.startsWith("/travel/")) {
    event.respondWith(
      (async () => (await caches.match(request, { cacheName: APP, ignoreSearch: true })) || fetch(request))(),
    );
  }
});
