import { useEffect, useSyncExternalStore } from "react";

import { Unauthorised, signIn } from "./api";
import { CHECK_MS, REFRESH_MS } from "./fresh";
import { Queued } from "./offline";
import { forgetSeen, keep } from "./persist";

export interface Resource<T> {
  data: T | undefined;
  error: Error | null;
  loading: boolean;
  revalidating: boolean;
  refresh: () => Promise<void>;
}

export interface ResourceOptions<T> {
  staleMs?: number;
  persist?: boolean;
  initial?: () => T | undefined;
}

interface Snapshot {
  data: unknown;
  error: Error | null;
  revalidating: boolean;
}

interface Entry {
  data: unknown;
  error: Error | null;
  at: number;
  asked: number;
  epoch: number;
  inflight: Promise<void> | null;
  pending: number;
  queue: Promise<unknown>;
  listeners: Set<() => void>;
  subscribe: (listener: () => void) => () => void;
  fetcher: (() => Promise<unknown>) | null;
  staleMs: number;
  persist: boolean;
  snapshot: Snapshot;
}

const DEFAULT_STALE_MS = 30_000;
const store = new Map<string, Entry>();

function entry(key: string): Entry {
  let found = store.get(key);
  if (!found) {
    const listeners = new Set<() => void>();
    found = {
      data: undefined,
      error: null,
      at: 0,
      asked: 0,
      epoch: 0,
      inflight: null,
      pending: 0,
      queue: Promise.resolve(),
      listeners,
      subscribe: (listener) => {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      fetcher: null,
      staleMs: DEFAULT_STALE_MS,
      persist: false,
      snapshot: { data: undefined, error: null, revalidating: false },
    };
    store.set(key, found);
  }
  return found;
}

function emit(e: Entry): void {
  e.snapshot = { data: e.data, error: e.error, revalidating: e.inflight !== null && e.data !== undefined };
  for (const listener of e.listeners) listener();
}

function write(key: string, data: unknown, fresh: boolean): void {
  const e = entry(key);
  e.data = data;
  e.error = null;
  e.at = fresh ? Date.now() : 0;
  emit(e);
  if (e.persist) keep(key, data);
}

const stale = (e: Entry) => e.data === undefined || Date.now() - e.at >= e.staleMs;

function signedOut(): void {
  void reset().finally(signIn);
}

function revalidate(key: string, fresh = false): Promise<void> {
  const e = entry(key);
  if (!e.fetcher) return Promise.resolve();
  if (fresh && e.inflight) {
    e.epoch += 1;
    e.inflight = null;
  }
  if (e.inflight) return e.inflight;
  e.asked = Date.now();
  const epoch = e.epoch;
  const read: Promise<void> = e
    .fetcher()
    .then(
      (data) => {
        if (e.epoch === epoch && e.pending === 0) write(key, data, true);
      },
      (error: unknown) => {
        if (error instanceof Unauthorised) return signedOut();
        if (e.epoch === epoch) e.error = error instanceof Error ? error : new Error(String(error));
      },
    )
    .finally(() => {
      if (e.inflight === read) e.inflight = null;
      emit(e);
    });
  e.inflight = read;
  emit(e);
  return read;
}

let watching = false;
let timer: number | undefined;

const due = (e: Entry, now: number) =>
  e.listeners.size > 0 && e.inflight === null && now - Math.max(e.at, e.asked) >= Math.max(e.staleMs, REFRESH_MS);

function watch(): void {
  if (watching || typeof document === "undefined") return;
  watching = true;
  const again = () => {
    for (const [key, e] of store) if (e.listeners.size > 0 && stale(e)) void revalidate(key);
  };
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && again());
  window.addEventListener("online", again);
  timer = window.setInterval(() => {
    if (document.visibilityState !== "visible") return;
    const now = Date.now();
    for (const [key, e] of store) if (due(e, now)) void revalidate(key);
  }, CHECK_MS);
}

export function useResource<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  options: ResourceOptions<T> = {},
): Resource<T> {
  const e = key === null ? null : entry(key);
  if (e) {
    e.fetcher = fetcher;
    e.staleMs = options.staleMs ?? DEFAULT_STALE_MS;
    if (options.persist) e.persist = true;
    if (e.data === undefined && options.initial) {
      const initial = options.initial();
      if (initial !== undefined) {
        e.data = initial;
        e.snapshot = { ...e.snapshot, data: initial };
      }
    }
  }
  const snapshot = useSyncExternalStore(
    e ? e.subscribe : noSubscribe,
    () => (e ? e.snapshot : EMPTY),
    () => (e ? e.snapshot : EMPTY),
  );
  useEffect(() => {
    if (key === null) return;
    watch();
    if (stale(entry(key))) void revalidate(key);
  }, [key]);
  return {
    data: snapshot.data as T | undefined,
    error: snapshot.error,
    loading: key !== null && snapshot.data === undefined && snapshot.error === null,
    revalidating: snapshot.revalidating,
    refresh: () => (key === null ? Promise.resolve() : refresh(key)),
  };
}

const EMPTY: Snapshot = { data: undefined, error: null, revalidating: false };
const noSubscribe = () => () => undefined;

function refresh(key: string): Promise<void> {
  entry(key).at = 0;
  return revalidate(key, true);
}

export async function mutate<T>(
  key: string,
  next?: T | ((current: T | undefined) => T),
  options: { request?: () => Promise<T | void> } = {},
): Promise<void> {
  const e = entry(key);
  e.epoch += 1;
  const before = e.data;
  const { request } = options;
  if (next !== undefined) {
    const value = typeof next === "function" ? (next as (current: T | undefined) => T)(e.data as T | undefined) : next;
    write(key, value, request === undefined);
  }
  if (!request) return;
  const mine = e.epoch;
  e.pending += 1;
  const sent = e.queue.then(request);
  e.queue = sent.catch(() => undefined);
  try {
    const result = await sent;
    e.pending -= 1;
    if (e.pending > 0) return;
    if (e.epoch !== mine) void refresh(key);
    else if (result !== undefined) write(key, result, true);
  } catch (error) {
    e.pending -= 1;
    if (error instanceof Unauthorised) {
      signedOut();
      throw error;
    }
    if (error instanceof Queued) return;
    if (e.epoch === mine) write(key, before, false);
    else if (e.pending === 0) void refresh(key);
    throw error;
  }
}

export function invalidate(prefix: string): void {
  for (const [key, e] of store) {
    if (!key.startsWith(prefix)) continue;
    e.at = 0;
    if (e.listeners.size > 0) void revalidate(key, true);
    else if (e.inflight) {
      e.epoch += 1;
      e.inflight = null;
    }
  }
}

export function prime<T>(key: string, value: T): void {
  write(key, value, true);
}

export function remember<T>(key: string, value: T): void {
  entry(key).persist = true;
  write(key, value, true);
}

export function peek<T>(key: string): T | undefined {
  return store.get(key)?.data as T | undefined;
}

export function seed(seen: Record<string, unknown>): void {
  for (const [key, data] of Object.entries(seen)) {
    const e = entry(key);
    e.persist = true;
    if (e.data !== undefined) continue;
    e.data = data;
    e.at = 0;
    emit(e);
  }
}

export function reset(): Promise<void> {
  for (const e of store.values()) {
    e.data = undefined;
    e.error = null;
    e.at = 0;
    e.epoch += 1;
    e.inflight = null;
    emit(e);
  }
  const forgotten = forgetSeen();
  for (const [key, e] of store) if (e.listeners.size > 0) void revalidate(key);
  return forgotten;
}

export function clearForTests(): void {
  store.clear();
  watching = false;
  if (timer !== undefined) window.clearInterval(timer);
  timer = undefined;
}
