import { type NewOp, SyncQueue, isPermanent, retryDelay } from "./queue";

function memory() {
  const data = new Map<string, string>();
  return { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => void data.set(key, value) };
}

function set(number: number, reps = 8): NewOp {
  return {
    key: `set:e1:${number}`,
    session: "s1",
    method: "PUT",
    path: `/sessions/s1/exercises/e1/sets/${number}`,
    body: { reps, weight: 60, confirmed_at: "2026-09-15T17:00:00Z" },
  };
}

function reply(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), { status });
}

function network() {
  const sent: { path: string; body: unknown }[] = [];
  let up = true;
  const fetcher = (async (url: string, init: RequestInit) => {
    if (!up) throw new TypeError("Failed to fetch");
    sent.push({ path: url, body: JSON.parse(String(init.body)) });
    return reply(200, { id: "e1" });
  }) as unknown as typeof fetch;
  return { sent, fetcher, cut: () => (up = false), restore: () => (up = true) };
}

function manualTimers() {
  const scheduled: { run: () => void; ms: number }[] = [];
  return {
    scheduled,
    schedule: (run: () => void, ms: number) => scheduled.push({ run, ms }),
    cancel: () => undefined,
  };
}

describe("the set queue", () => {
  it("sends in order and empties", async () => {
    const net = network();
    const queue = new SyncQueue({ fetcher: net.fetcher, storage: null });

    queue.enqueue(set(1));
    queue.enqueue(set(2));
    await queue.flush();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(net.sent.map((request) => request.path)).toEqual([
      "/api/training/sessions/s1/exercises/e1/sets/1",
      "/api/training/sessions/s1/exercises/e1/sets/2",
    ]);
    expect(queue.hasPending()).toBe(false);
    expect(queue.stateOf("set:e1:1")).toBe("saved");
  });

  it("offline the set stays pending, in amber, and goes on its own when back", async () => {
    const net = network();
    const timers = manualTimers();
    const queue = new SyncQueue({ fetcher: net.fetcher, storage: null, ...timers });

    net.cut();
    queue.enqueue(set(1));
    await queue.flush();

    expect(queue.stateOf("set:e1:1")).toBe("pending");
    expect(timers.scheduled.at(-1)?.ms).toBe(1000);

    net.restore();
    timers.scheduled.at(-1)?.run();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(queue.hasPending()).toBe(false);
    expect(net.sent).toHaveLength(1);
  });

  it("the wait grows up to thirty seconds", () => {
    expect([1, 2, 3, 6, 10].map(retryDelay)).toEqual([1000, 2000, 4000, 30000, 30000]);
  });

  it("reloading halfway does not lose what was not sent", async () => {
    const storage = memory();
    const net = network();
    net.cut();
    const before = new SyncQueue({ fetcher: net.fetcher, storage, ...manualTimers() });
    before.enqueue(set(1));
    await before.flush();

    const after = new SyncQueue({ fetcher: net.fetcher, storage, ...manualTimers() });

    expect(after.pending("s1").map((op) => op.key)).toEqual(["set:e1:1"]);
  });

  it("correcting a set not yet sent replaces it: the latest wins", async () => {
    const net = network();
    net.cut();
    const queue = new SyncQueue({ fetcher: net.fetcher, storage: null, ...manualTimers() });
    queue.enqueue(set(1, 8));
    await queue.flush();
    queue.enqueue(set(1, 9));

    expect(queue.pending()).toHaveLength(1);
    expect(queue.pending()[0]?.body.reps).toBe(9);
  });

  it("what the server rejects is removed, with its exercise and sets, and it warns", async () => {
    const fetcher = (async () => reply(409, { detail: "this slot does not allow two variants" })) as unknown as typeof fetch;
    const queue = new SyncQueue({ fetcher, storage: null });
    const events: string[] = [];
    queue.listen((event) => events.push(event.type === "rejected" ? event.detail : event.type));

    queue.enqueue({ key: "exercise:e1", session: "s1", method: "PUT", path: "/sessions/s1/exercises/e1", body: {} });
    queue.enqueue(set(1));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(queue.hasPending()).toBe(false);
    expect(events).toEqual(["this slot does not allow two variants"]);
  });

  it("if a session started offline could not start, what was logged in it goes with it", async () => {
    const fetcher = (async () => reply(409, { detail: "there is already a session in progress" })) as unknown as typeof fetch;
    const queue = new SyncQueue({ fetcher, storage: null });

    queue.enqueue({ key: "start:s1", session: "s1", method: "PUT", path: "/sessions/s1", body: {} });
    queue.enqueue({ key: "exercise:e1", session: "s1", method: "PUT", path: "/sessions/s1/exercises/e1", body: {} });
    queue.enqueue(set(1));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(queue.hasPending()).toBe(false);
  });

  it("if the exercise already existed with another id, its sets are re-pointed", async () => {
    const sent: string[] = [];
    const fetcher = (async (url: string) => {
      sent.push(url);
      return reply(200, { id: "e2" });
    }) as unknown as typeof fetch;
    const queue = new SyncQueue({ fetcher, storage: null });

    queue.enqueue({ key: "exercise:e1", session: "s1", method: "PUT", path: "/sessions/s1/exercises/e1", body: {} });
    queue.enqueue(set(1));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(sent).toEqual(["/api/training/sessions/s1/exercises/e1", "/api/training/sessions/s1/exercises/e2/sets/1"]);
  });

  it("the note travels with its exercise if it is re-pointed", async () => {
    const sent: string[] = [];
    const fetcher = (async (url: string) => {
      sent.push(url);
      return reply(200, { id: "e2" });
    }) as unknown as typeof fetch;
    const queue = new SyncQueue({ fetcher, storage: null });

    queue.enqueue({ key: "exercise:e1", session: "s1", method: "PUT", path: "/sessions/s1/exercises/e1", body: {} });
    queue.enqueue({ key: "notes:e1", session: "s1", method: "PUT", path: "/sessions/s1/exercises/e1/notes", body: { notes: "x" } });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(sent).toEqual(["/api/training/sessions/s1/exercises/e1", "/api/training/sessions/s1/exercises/e2/notes"]);
  });

  it("408 and 429 are retried; the rest of 4xx are not", () => {
    expect([400, 404, 409, 422].every(isPermanent)).toBe(true);
    expect([0, 408, 429, 500, 503].some(isPermanent)).toBe(false);
  });

  it("with the sign-in expired it drops no set: it keeps it and asks to sign in again", async () => {
    const storage = memory();
    const events: string[] = [];
    let signedIn = false;
    const fetcher = (async () => (signedIn ? reply(200, { id: "e1" }) : reply(401, { login: "/login" }))) as unknown as typeof fetch;
    const timers = manualTimers();
    const queue = new SyncQueue({ fetcher, storage, ...timers });
    queue.listen((event) => events.push(event.type));

    queue.enqueue(set(1));
    queue.enqueue(set(2));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(events).toEqual(["signed-out"]);
    expect(queue.pending().map((op) => op.key)).toEqual(["set:e1:1", "set:e1:2"]);

    signedIn = true;
    const reopened = new SyncQueue({ fetcher, storage, ...manualTimers() });
    await reopened.flush();

    expect(reopened.hasPending()).toBe(false);
  });
});

describe("forgetting a deleted session", () => {
  it("removes what is pending for that session and keeps the rest", async () => {
    const net = network();
    net.cut();
    const queue = new SyncQueue({ fetcher: net.fetcher, storage: null, ...manualTimers() });
    queue.enqueue(set(1));
    await queue.flush();
    queue.enqueue({ ...set(2), session: "other", key: "set:e9:1" });
    await new Promise((resolve) => setTimeout(resolve, 0));

    queue.forget("s1");

    expect(queue.pending().map((op) => op.session)).toEqual(["other"]);
  });
});

describe("whose pending work it is", () => {
  it("if another person signs in, the previous one's is dropped without being sent", () => {
    const storage = memory();
    const net = network();
    net.cut();
    const queue = new SyncQueue({ fetcher: net.fetcher, storage, schedule: () => undefined });

    queue.bindPerson("ana");
    queue.enqueue(set(1));
    queue.bindPerson("ana");
    expect(queue.hasPending()).toBe(true);

    const reopened = new SyncQueue({ fetcher: net.fetcher, storage, schedule: () => undefined });
    reopened.bindPerson("bea");
    expect(reopened.hasPending()).toBe(false);
  });
});
