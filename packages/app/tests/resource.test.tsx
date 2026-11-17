// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { invalidate, mutate, peek, prime, reset, useResource } from "../src/index";
import { clearForTests } from "../src/resource";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

let root: Root;
let host: HTMLElement;

beforeEach(() => {
  clearForTests();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function later<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((ok, ko) => {
    resolve = ok;
    reject = ko;
  });
  return { promise, resolve, reject };
}

const flush = () => act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
});

function Shows({ name, fetcher, staleMs }: { name: string; fetcher: () => Promise<string[]>; staleMs?: number }) {
  const { data, loading } = useResource("books", fetcher, { staleMs });
  return <p data-name={name}>{loading ? "cargando" : (data ?? []).join(",")}</p>;
}

const text = (name: string) => host.querySelector(`[data-name=${name}]`)?.textContent;

describe("useResource", () => {
  it("two screens with the same key make a single request", async () => {
    const fetcher = vi.fn(async () => ["a"]);
    act(() =>
      root.render(
        <>
          <Shows name="one" fetcher={fetcher} />
          <Shows name="two" fetcher={fetcher} />
        </>,
      ),
    );
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(text("one")).toBe("a");
    expect(text("two")).toBe("a");
  });

  it("going back to a tab requests nothing and shows no skeleton", async () => {
    const fetcher = vi.fn(async () => ["a"]);
    function Tabs() {
      const [tab, setTab] = useState("shelf");
      return (
        <>
          <button onClick={() => setTab(tab === "shelf" ? "stats" : "shelf")}>cambiar</button>
          {tab === "shelf" && <Shows name="shelf" fetcher={fetcher} />}
        </>
      );
    }
    act(() => root.render(<Tabs />));
    await flush();
    const button = host.querySelector("button")!;
    act(() => button.click());
    act(() => button.click());
    expect(text("shelf")).toBe("a");
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("the old data shows while it rereads, and coming back to the app rereads", async () => {
    let round = 0;
    const fetcher = vi.fn(async () => [`v${++round}`]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} staleMs={0} />));
    await flush();
    expect(text("one")).toBe("v1");

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(text("one")).toBe("v1");
    await flush();
    expect(text("one")).toBe("v2");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("after reset, a hung read does not make the next one wait", async () => {
    const hung = vi.fn(() => new Promise<string[]>(() => undefined));
    act(() => root.render(<Shows name="one" fetcher={hung} />));
    act(() => root.unmount());
    reset();

    root = createRoot(host);
    act(() => root.render(<Shows name="one" fetcher={async () => ["otra persona"]} />));
    await flush();
    expect(text("one")).toBe("otra persona");
  });

  it("after reset, what is on screen is requested again, without waiting to come back to the app", async () => {
    let who = "first";
    act(() => root.render(<Shows name="one" fetcher={async () => [who]} />));
    await flush();
    who = "second";
    await act(async () => {
      await reset();
    });
    await flush();
    expect(text("one")).toBe("second");
  });

  it("on the server it renders without touching anything", () => {
    const fetcher = vi.fn(async () => ["a"]);
    expect(renderToString(<Shows name="ssr" fetcher={fetcher} />)).toContain("cargando");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("shows what is known under another key while its own arrives", async () => {
    prime("books", [{ id: "1", title: "Kasus" }]);
    const reply = later<{ id: string; title: string; pages: number }>();
    function Book() {
      const { data } = useResource("book:1", () => reply.promise, {
        initial: () => peek<{ id: string; title: string }[]>("books")?.find((one) => one.id === "1") as never,
      });
      return <p data-name="book">{data?.title}</p>;
    }
    act(() => root.render(<Book />));
    expect(text("book")).toBe("Kasus");
    reply.resolve({ id: "1", title: "Kasus", pages: 200 });
    await flush();
    expect(text("book")).toBe("Kasus");
  });
});

describe("invalidate", () => {
  it("a read that left before the change, with nobody looking, arrives and is dropped", async () => {
    const old = later<string[]>();
    let calls = 0;
    const fetcher = () => (++calls === 1 ? old.promise : Promise.resolve(["after"]));
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    act(() => root.unmount());
    invalidate("");
    old.resolve(["before"]);
    await flush();
    expect(peek<string[]>("books")).toBeUndefined();

    root = createRoot(host);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    await flush();
    expect(text("one")).toBe("after");
  });
});

describe("mutate", () => {
  it("renders before the answer and goes back to the previous state if it fails", async () => {
    act(() => root.render(<Shows name="one" fetcher={async () => ["a"]} />));
    await flush();

    const reply = later<string[]>();
    let failed: unknown = null;
    void act(() => {
      void mutate<string[]>("books", (all) => [...(all ?? []), "b"], { request: () => reply.promise }).catch(
        (error: unknown) => (failed = error),
      );
    });
    expect(text("one")).toBe("a,b");
    reply.reject(new Error("no"));
    await flush();
    expect(text("one")).toBe("a");
    expect((failed as Error).message).toBe("no");
  });

  it("a read that left before the write arrives stale and is dropped", async () => {
    const read = later<string[]>();
    act(() => root.render(<Shows name="one" fetcher={() => read.promise} />));
    await act(async () => {
      await mutate("books", ["escrito"]);
    });
    read.resolve(["read before"]);
    await flush();
    expect(text("one")).toBe("escrito");
  });

  it("writes queue up and two taps in a row both stay", async () => {
    act(() => root.render(<Shows name="one" fetcher={async () => []} />));
    await flush();

    const first = later<string[]>();
    const second = later<string[]>();
    const sent: string[] = [];
    let a!: Promise<void>;
    let b!: Promise<void>;
    act(() => {
      a = mutate<string[]>("books", (all) => [...(all ?? []), "a"], {
        request: () => {
          sent.push("a");
          return first.promise;
        },
      });
      b = mutate<string[]>("books", (all) => [...(all ?? []), "b"], {
        request: () => {
          sent.push("b");
          return second.promise;
        },
      });
    });
    await flush();
    expect(sent).toEqual(["a"]);
    expect(text("one")).toBe("a,b");

    first.resolve(["a"]);
    await flush();
    expect(sent).toEqual(["a", "b"]);
    expect(text("one")).toBe("a,b");

    second.resolve(["a", "b"]);
    await act(async () => {
      await Promise.all([a, b]);
    });
    expect(text("one")).toBe("a,b");
  });

  it("an answer arriving after another write does not overwrite it, and it rereads", async () => {
    let server = ["a"];
    act(() => root.render(<Shows name="one" fetcher={async () => server} />));
    await flush();

    const tap = later<string[]>();
    let sent!: Promise<void>;
    act(() => {
      sent = mutate<string[]>("books", ["a", "tachado"], { request: () => tap.promise });
    });
    act(() => void mutate("books", ["a", "tachado", "leche"]));
    server = ["a", "tachado", "leche"];
    tap.resolve(["a", "tachado"]);
    await act(async () => {
      await sent;
    });
    await flush();
    expect(text("one")).toBe("a,tachado,leche");
  });

  it("invalidate does not settle for a read that left before the change", async () => {
    const first = later<string[]>();
    const fetcher = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(["nuevo"]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    act(() => invalidate("books"));
    first.resolve(["viejo"]);
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(text("one")).toBe("nuevo");
  });

  it("invalidate rereads what is on screen", async () => {
    let round = 0;
    const fetcher = vi.fn(async () => [`v${++round}`]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    await flush();
    act(() => invalidate("book"));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(text("one")).toBe("v2");
  });
});

describe("what is seen while looking", () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] }));
  afterEach(() => vi.useRealTimers());

  it("it is requested again every five minutes without touching anything, and not before", async () => {
    let round = 0;
    const fetcher = vi.fn(async () => [`vuelta ${++round}`]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    await flush();
    expect(text("one")).toBe("vuelta 1");

    await act(async () => vi.advanceTimersByTime(4 * 60_000));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTime(60_000 + 15_000));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(text("one")).toBe("vuelta 2");
  });

  it("hidden it requests nothing, and what lasts longer than five minutes waits its turn", async () => {
    const hidden = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const books = vi.fn(async () => ["a"]);
    const catalogue = vi.fn(async () => ["b"]);
    function Both() {
      useResource("books", books);
      useResource("catalogue", catalogue, { staleMs: Infinity });
      return null;
    }
    act(() => root.render(<Both />));
    await flush();

    await act(async () => vi.advanceTimersByTime(10 * 60_000));
    await flush();
    expect(books).toHaveBeenCalledTimes(1);

    hidden.mockReturnValue("visible");
    await act(async () => vi.advanceTimersByTime(15_000));
    await flush();
    expect(books).toHaveBeenCalledTimes(2);
    expect(catalogue).toHaveBeenCalledTimes(1);
    hidden.mockRestore();
  });

  it("what is not on screen is not requested", async () => {
    const fetcher = vi.fn(async () => ["a"]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    await flush();
    act(() => root.render(<></>));

    await act(async () => vi.advanceTimersByTime(10 * 60_000));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
