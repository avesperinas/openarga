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
  it("dos pantallas con la misma clave hacen una sola petición", async () => {
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

  it("volver a una pestaña no pide nada ni enseña el esqueleto", async () => {
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

  it("lo viejo se enseña mientras se relee, y al volver a la app se relee", async () => {
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

  it("tras reset, una lectura que se quedó colgada no hace esperar a la siguiente", async () => {
    const hung = vi.fn(() => new Promise<string[]>(() => undefined));
    act(() => root.render(<Shows name="one" fetcher={hung} />));
    act(() => root.unmount());
    reset();

    root = createRoot(host);
    act(() => root.render(<Shows name="one" fetcher={async () => ["otra persona"]} />));
    await flush();
    expect(text("one")).toBe("otra persona");
  });

  it("tras reset, lo que está en pantalla se pide otra vez, sin esperar a volver a la app", async () => {
    let who = "una";
    act(() => root.render(<Shows name="one" fetcher={async () => [who]} />));
    await flush();
    who = "otra";
    await act(async () => {
      await reset();
    });
    await flush();
    expect(text("one")).toBe("otra");
  });

  it("en el servidor pinta sin tocar nada", () => {
    const fetcher = vi.fn(async () => ["a"]);
    expect(renderToString(<Shows name="ssr" fetcher={fetcher} />)).toContain("cargando");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("enseña lo que se sabe de otra clave mientras llega lo suyo", async () => {
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
  it("una lectura que salió antes del cambio, sin nadie mirando, llega y se tira", async () => {
    const old = later<string[]>();
    let calls = 0;
    const fetcher = () => (++calls === 1 ? old.promise : Promise.resolve(["después"]));
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    act(() => root.unmount());
    invalidate("");
    old.resolve(["antes"]);
    await flush();
    expect(peek<string[]>("books")).toBeUndefined();

    root = createRoot(host);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    await flush();
    expect(text("one")).toBe("después");
  });
});

describe("mutate", () => {
  it("pinta antes de que conteste y vuelve a lo de antes si falla", async () => {
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

  it("una lectura que salió antes de escribir llega vieja y se tira", async () => {
    const read = later<string[]>();
    act(() => root.render(<Shows name="one" fetcher={() => read.promise} />));
    await act(async () => {
      await mutate("books", ["escrito"]);
    });
    read.resolve(["leído antes"]);
    await flush();
    expect(text("one")).toBe("escrito");
  });

  it("las escrituras van en fila y dos toques seguidos quedan los dos", async () => {
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

  it("una respuesta que llega después de otra escritura no la pisa, y se relee", async () => {
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

  it("invalidate no se conforma con una lectura que salió antes del cambio", async () => {
    const first = later<string[]>();
    const fetcher = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(["nuevo"]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    act(() => invalidate("books"));
    first.resolve(["viejo"]);
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(text("one")).toBe("nuevo");
  });

  it("invalidate relee lo que está en pantalla", async () => {
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

describe("lo que se ve mientras se mira", () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] }));
  afterEach(() => vi.useRealTimers());

  it("se vuelve a pedir cada cinco minutos sin tocar nada, y no antes", async () => {
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

  it("escondida no pide nada, y lo que dura más de cinco minutos espera lo suyo", async () => {
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

  it("lo que no está en pantalla no se pide", async () => {
    const fetcher = vi.fn(async () => ["a"]);
    act(() => root.render(<Shows name="one" fetcher={fetcher} />));
    await flush();
    act(() => root.render(<></>));

    await act(async () => vi.advanceTimersByTime(10 * 60_000));
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
