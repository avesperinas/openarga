// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NeedsNetwork, Queued, createOfflineQueue, memoryStore, repeatable } from "../src/offline";

type Reply = Response | Error;

let me = "persona-a";

function network(...replies: Reply[]) {
  const asked: string[] = [];
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/prueba/me") return new Response(JSON.stringify({ user_id: me }), { status: 200 });
    asked.push(`${init?.method} ${url}`);
    const reply = replies.shift() ?? new Response("{}", { status: 200 });
    if (reply instanceof Error) throw reply;
    return reply;
  });
  return { asked, fetcher: fetcher as unknown as typeof fetch };
}

const ok = () => new Response(JSON.stringify({ ok: true }), { status: 200 });
const down = () => new TypeError("no network");

beforeEach(() => {
  localStorage.clear();
  me = "persona-a";
});

async function queueWith(...replies: Reply[]) {
  const net = network(...replies);
  const queue = createOfflineQueue({ app: "prueba", store: memoryStore(), fetcher: net.fetcher });
  await queue.bindPerson("persona-a");
  return { ...net, queue };
}

describe("what can be replayed", () => {
  it("edits and deletions yes; a creation, only with its id", () => {
    expect(repeatable("PUT", { in_cart: true })).toBe(true);
    expect(repeatable("DELETE", undefined)).toBe(true);
    expect(repeatable("POST", { name: "Leche" })).toBe(false);
    expect(repeatable("POST", { id: "x" })).toBe(true);
    expect(repeatable("POST", { items: [{ id: "x", name: "Leche" }] })).toBe(true);
    expect(repeatable("POST", { items: [{ id: "x" }, { name: "Pan" }] })).toBe(false);
    expect(repeatable("PATCH", { done: true })).toBe(false);
  });
});

describe("the offline queue", () => {
  it("online, it sends and answers", async () => {
    const { queue, asked } = await queueWith(ok());
    expect(await queue.send("/api/prueba/a", "PUT", { x: 1 })).toEqual({ ok: true });
    expect(asked).toEqual(["PUT /api/prueba/a"]);
    expect(queue.state().pending).toBe(0);
  });

  it("offline it keeps what is replayable and sends it in order when back", async () => {
    const { queue, asked } = await queueWith(down(), down());
    await expect(queue.send("/api/prueba/a", "PUT", { x: 1 }, { what: "a" })).rejects.toBeInstanceOf(Queued);
    await expect(queue.send("/api/prueba/b", "POST", { id: "b" }, { what: "b" })).rejects.toBeInstanceOf(Queued);
    expect(queue.state().pending).toBe(2);

    const sent = vi.fn();
    queue.onSent(sent);
    const flushed = await queue.flush(true);
    expect(flushed).toEqual({ sent: 2, signedOut: false, offline: false });
    expect(asked.slice(-2)).toEqual(["PUT /api/prueba/a", "POST /api/prueba/b"]);
    expect(queue.state().pending).toBe(0);
    expect(sent).toHaveBeenCalledOnce();
  });

  it("what cannot be replayed says it needs the network", async () => {
    const { queue } = await queueWith(down());
    await expect(queue.send("/api/prueba/a", "POST", { name: "Leche" })).rejects.toBeInstanceOf(NeedsNetwork);
    expect(queue.state().pending).toBe(0);
  });

  it("without a session or with the server down it stops and keeps everything", async () => {
    const { queue } = await queueWith(down(), new Response(null, { status: 401 }), new Response(null, { status: 503 }));
    await queue.send("/api/prueba/a", "PUT", {}).catch(() => undefined);

    expect(await queue.flush()).toEqual({ sent: 0, signedOut: true, offline: false });
    expect(queue.state()).toMatchObject({ pending: 1, signedOut: true });
    expect((await queue.flush(true)).offline).toBe(true);
    expect(queue.state().pending).toBe(1);
  });

  it("what is refused is set aside with its reason, the rest goes on, and it can be retried or forgotten", async () => {
    const refusal = new Response(JSON.stringify({ detail: "it is no longer on the list" }), { status: 404 });
    const { queue } = await queueWith(down(), down(), refusal, ok(), ok());
    await queue.send("/api/prueba/a", "PUT", {}, { what: "tick the bread" }).catch(() => undefined);
    await queue.send("/api/prueba/b", "PUT", {}, { what: "marcar la leche" }).catch(() => undefined);

    expect(await queue.flush(true)).toEqual({ sent: 1, signedOut: false, offline: false });
    const [refused] = queue.state().refused;
    expect(refused).toMatchObject({ what: "tick the bread", problem: "it is no longer on the list" });

    await queue.retry(refused!.key!);
    expect(queue.state()).toMatchObject({ pending: 0, refused: [] });
  });

  it("if another person signs in, the previous one's queue is dropped", async () => {
    const { queue } = await queueWith(down());
    await queue.send("/api/prueba/a", "PUT", {}).catch(() => undefined);
    expect(queue.state().pending).toBe(1);

    await queue.bindPerson("persona-b");
    expect(queue.state().pending).toBe(0);
  });

  it("it sends nothing until it knows who is looking, nor with another person's session", async () => {
    const net = network(down());
    const queue = createOfflineQueue({ app: "prueba", store: memoryStore(), fetcher: net.fetcher });
    await expect(queue.send("/api/prueba/a", "PUT", {})).rejects.toBeInstanceOf(NeedsNetwork);

    const { queue: other, asked } = await queueWith(down());
    await other.send("/api/prueba/a", "PUT", {}).catch(() => undefined);
    me = "persona-b";
    expect((await other.flush(true)).sent).toBe(0);
    expect(asked).toEqual(["PUT /api/prueba/a"]);
    expect(other.state().pending).toBe(0);
  });
});
