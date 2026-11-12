import { SIZES, spanOf } from "@openarga/ui";
import { describe, expect, it } from "vitest";

import type { DeskItem, LayoutItem, WidgetSize } from "./kernel";
import {
  BREAKPOINTS,
  COLUMNS,
  type Desk,
  add,
  arrange,
  arrangeAll,
  autoArrange,
  cellAt,
  cellNear,
  clampToGrid,
  createPage,
  firstFit,
  isArrangedByHand,
  move,
  movePage,
  nearestSize,
  remove,
  removePage,
  resize,
} from "./layout";

const widget = (id: string, size: WidgetSize = "2x2"): DeskItem => ({
  instance_id: id,
  source: "kernel",
  widget: "events",
  size,
});

const placed = (id: string, x = 0, y = 0, size: WidgetSize = "2x2"): LayoutItem => ({
  ...widget(id, size),
  x,
  y,
});

const desk = (): Desk => ({
  pages: [
    { id: "inicio", items: [widget("a"), widget("b")] },
    { id: "dos", items: [widget("c")] },
  ],
  placements: {},
});

const at = (desk: Desk, breakpoint: keyof typeof COLUMNS, page: number, id: string) =>
  arrangeAll(desk, breakpoint)[page]!.items.find((item) => item.instance_id === id)!;

function random(seed: number) {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 2 ** 32;
    return state / 2 ** 32;
  };
}

const overlapping = (items: LayoutItem[]) =>
  items.some((a, i) =>
    items.slice(i + 1).some((b) => {
      const [aw, ah] = spanOf(a.size);
      const [bw, bh] = spanOf(b.size);
      return a.x < b.x + bw && a.x + aw > b.x && a.y < b.y + bh && a.y + ah > b.y;
    }),
  );

describe("el mismo escritorio en cualquier formato", () => {
  it("salen las mismas pantallas con los mismos widgets, sin solapes y dentro de la rejilla", () => {
    const next = random(46);
    for (let round = 0; round < 200; round++) {
      const pages = Array.from({ length: 1 + Math.floor(next() * 4) }, (_, p) => ({
        id: `p${p}`,
        items: Array.from({ length: Math.floor(next() * 9) }, (_, i) =>
          widget(`w${p}-${i}`, SIZES[Math.floor(next() * SIZES.length)]!),
        ),
      }));
      const placements = Object.fromEntries(
        BREAKPOINTS.filter(() => next() < 0.5).map((breakpoint) => [
          breakpoint,
          Object.fromEntries(
            pages.map((page) => [
              page.id,
              Object.fromEntries(
                page.items
                  .filter(() => next() < 0.6)
                  .map((item) => [
                    item.instance_id,
                    [Math.floor(next() * 14), Math.floor(next() * 6)] as [number, number],
                  ]),
              ),
            ]),
          ),
        ]),
      );
      const desktop: Desk = { pages, placements };

      for (const breakpoint of BREAKPOINTS) {
        const arranged = arrangeAll(desktop, breakpoint);
        expect(arranged.map((page) => page.id)).toEqual(pages.map((page) => page.id));
        arranged.forEach((page, index) => {
          expect(page.items.map((item) => item.instance_id)).toEqual(
            pages[index]!.items.map((item) => item.instance_id),
          );
          expect(overlapping(page.items)).toBe(false);
          for (const item of page.items) {
            expect(item.x + spanOf(item.size)[0]).toBeLessThanOrEqual(COLUMNS[breakpoint]);
          }
        });
      }
    }
  });

  it("sin nada a mano, se coloca en orden: dos por fila en el móvil y en una en el ordenador", () => {
    const hoy = { id: "hoy", items: [widget("a"), widget("b"), widget("c", "4x2")] };

    expect(arrange(hoy, 4).map(({ x, y }) => [x, y])).toEqual([
      [0, 0],
      [2, 0],
      [0, 2],
    ]);
    expect(arrange(hoy, 12).map(({ x, y }) => [x, y])).toEqual([
      [0, 0],
      [2, 0],
      [4, 0],
    ]);
  });

  it("lo colocado a mano se respeta, y lo demás se coloca alrededor", () => {
    const hoy = { id: "hoy", items: [widget("a"), widget("b")] };

    const arranged = arrange(hoy, 12, { b: [6, 0] });

    expect(arranged.find((i) => i.instance_id === "b")).toMatchObject({ x: 6, y: 0 });
    expect(arranged.find((i) => i.instance_id === "a")).toMatchObject({ x: 0, y: 0 });
  });

  it("una posición a mano que no cabe en este ancho se coloca sola", () => {
    const hoy = { id: "hoy", items: [widget("a", "4x2")] };

    expect(arrange(hoy, 4, { a: [8, 0] })[0]).toMatchObject({ x: 0, y: 0 });
  });
});

describe("mover", () => {
  it("dentro de la misma pantalla deja la tarjeta donde cae y aparta a la que tapaba", () => {
    const moved = move(desk(), "b", "mobile", { page: 0, x: 0, y: 0 });

    expect(at(moved, "mobile", 0, "b")).toMatchObject({ x: 0, y: 0 });
    expect(at(moved, "mobile", 0, "a")).toMatchObject({ x: 2, y: 0 });
    expect(moved.pages[0]!.items).toHaveLength(2);
  });

  it("queda colocada a mano en ese formato y en los demás no", () => {
    const moved = move(desk(), "a", "desktop", { page: 0, x: 8, y: 0 });

    expect(isArrangedByHand(moved, "desktop", "inicio")).toBe(true);
    expect(isArrangedByHand(moved, "mobile", "inicio")).toBe(false);
    expect(at(moved, "desktop", 0, "a")).toMatchObject({ x: 8, y: 0 });
  });

  it("los formatos que se colocan solos siguen el orden nuevo", () => {
    const moved = move(desk(), "b", "desktop", { page: 0, x: 0, y: 0 });

    expect(moved.pages[0]!.items.map((i) => i.instance_id)).toEqual(["b", "a"]);
    expect(at(moved, "mobile", 0, "b")).toMatchObject({ x: 0, y: 0 });
  });

  it("lo colocado a mano en otro formato no se mueve", () => {
    const enMovil = move(desk(), "b", "mobile", { page: 0, x: 0, y: 2 });
    const enOrdenador = move(enMovil, "a", "desktop", { page: 0, x: 10, y: 0 });

    expect(at(enOrdenador, "mobile", 0, "b")).toMatchObject({ x: 0, y: 2 });
  });

  it("a otra pantalla lo cambia de pantalla en todos los formatos", () => {
    const moved = move(desk(), "a", "tablet", { page: 1, x: 2, y: 0 });

    expect(moved.pages[0]!.items.map((i) => i.instance_id)).toEqual(["b"]);
    for (const breakpoint of BREAKPOINTS) {
      expect(arrangeAll(moved, breakpoint)[1]!.items.map((i) => i.instance_id).sort()).toEqual([
        "a",
        "c",
      ]);
    }
  });

  it("no mueve nada si la pantalla de destino no existe", () => {
    expect(move(desk(), "a", "mobile", { page: 9, x: 0, y: 0 })).toEqual(desk());
  });

  it("no deja coordenadas negativas ni fuera de la rejilla", () => {
    const moved = move(desk(), "a", "mobile", { page: 0, x: 3, y: -1 });

    expect(at(moved, "mobile", 0, "a")).toMatchObject({ x: 2, y: 0 });
  });
});

describe("colocar solo", () => {
  it("olvida lo hecho a mano en ese formato, y solo en ese", () => {
    const aMano = move(move(desk(), "a", "desktop", { page: 0, x: 8, y: 0 }), "b", "mobile", {
      page: 0,
      x: 0,
      y: 4,
    });

    const solo = autoArrange(aMano, "desktop", "inicio");

    expect(isArrangedByHand(solo, "desktop", "inicio")).toBe(false);
    expect(isArrangedByHand(solo, "mobile", "inicio")).toBe(true);
  });
});

describe("quitar", () => {
  it("lo saca de todas partes, también de lo colocado a mano", () => {
    const aMano = move(desk(), "a", "desktop", { page: 0, x: 8, y: 0 });

    const left = remove(aMano, "a");

    expect(left.pages[0]!.items.map((i) => i.instance_id)).toEqual(["b"]);
    expect(left.placements.desktop?.inicio).not.toHaveProperty("a");
  });
});

describe("añadir", () => {
  const entrada = widget("nuevo");

  it("lo pone al final de la pantalla que se le dice, y cada formato le busca hueco", () => {
    const aMano = move(desk(), "a", "mobile", { page: 0, x: 0, y: 2 });

    const next = add(aMano, 0, entrada);

    expect(next.pages[0]!.items.at(-1)!.instance_id).toBe("nuevo");
    expect(overlapping(arrangeAll(next, "mobile")[0]!.items)).toBe(false);
    expect(next.pages[1]!.items).toHaveLength(1);
  });

  it("no añade nada si la pantalla no existe", () => {
    expect(add(desk(), 9, entrada)).toEqual(desk());
  });
});

describe("cambiar de tamaño", () => {
  it("es en todos los formatos", () => {
    const next = resize(desk(), "a", "4x2");

    for (const breakpoint of BREAKPOINTS) {
      expect(at(next, breakpoint, 0, "a").size).toBe("4x2");
    }
  });

  it("recoloca en vez de solaparse con el vecino al crecer", () => {
    const aMano = move(desk(), "b", "mobile", { page: 0, x: 2, y: 0 });

    const next = resize(aMano, "a", "4x2");

    expect(overlapping(arrangeAll(next, "mobile")[0]!.items)).toBe(false);
  });
});

describe("pantallas", () => {
  it("se crean vacías y al final", () => {
    const next = createPage(desk(), "tres");

    expect(next.pages).toHaveLength(3);
    expect(next.pages[2]).toEqual({ id: "tres", items: [] });
  });

  it("se reordenan llevándose sus widgets", () => {
    const next = movePage(desk(), 1, 0);

    expect(next.pages.map((page) => page.id)).toEqual(["dos", "inicio"]);
  });

  it("no se reordenan a una posición que no existe", () => {
    expect(movePage(desk(), 0, 5)).toEqual(desk());
    expect(movePage(desk(), 0, -1)).toEqual(desk());
  });

  it("borrarla llevándose los widgets los pone al final de la anterior", () => {
    const next = removePage(desk(), 1, true);

    expect(next.pages).toHaveLength(1);
    expect(next.pages[0]!.items.map((i) => i.instance_id)).toEqual(["a", "b", "c"]);
    expect(at(next, "mobile", 0, "c")).toMatchObject({ x: 0, y: 2 });
  });

  it("borrarla sin llevárselos los borra con ella, y sus posiciones también", () => {
    const aMano = move(desk(), "c", "tablet", { page: 1, x: 4, y: 0 });

    const next = removePage(aMano, 1, false);

    expect(next.pages.map((p) => p.id)).toEqual(["inicio"]);
    expect(next.placements.tablet?.dos).toBeUndefined();
  });

  it("borrar la primera lleva sus widgets a la que pasa a serlo", () => {
    const next = removePage(desk(), 0, true);

    expect(next.pages.map((p) => p.id)).toEqual(["dos"]);
    expect(next.pages[0]!.items.map((i) => i.instance_id)).toEqual(["c", "a", "b"]);
  });

  it("nunca se queda sin ninguna", () => {
    const una: Desk = { pages: [desk().pages[0]!], placements: {} };

    expect(removePage(una, 0, false)).toEqual(una);
  });
});

describe("en qué celda cae un punto", () => {
  const rect = { left: 0, top: 0, width: 358, height: 358 };

  it("la primera columna es la 0", () => {
    expect(cellAt(rect, 4, 12, { x: 10, y: 10 })).toEqual({ x: 0, y: 0 });
  });

  it("la última no se sale de la rejilla", () => {
    expect(cellAt(rect, 4, 12, { x: 999, y: 10 }).x).toBe(3);
  });

  it("baja de fila cuando el punto baja", () => {
    expect(cellAt(rect, 4, 12, { x: 10, y: 120 }).y).toBe(1);
  });
});

describe("caber entero", () => {
  it("un 4x2 no puede empezar en la columna 2 de cuatro", () => {
    expect(clampToGrid(2, 4, 4)).toBe(0);
  });

  it("un 2x2 sí puede empezar en la 2", () => {
    expect(clampToGrid(2, 2, 4)).toBe(2);
  });
});

describe("primer hueco", () => {
  it("es el origen cuando la página está vacía", () => {
    expect(firstFit([], "2x2", 4)).toEqual({ x: 0, y: 0 });
  });

  it("salta lo ocupado y se coloca al lado", () => {
    expect(firstFit([placed("a")], "2x2", 4)).toEqual({ x: 2, y: 0 });
  });

  it("baja de fila cuando no queda ancho", () => {
    expect(firstFit([placed("a"), placed("b", 2)], "2x2", 4)).toEqual({ x: 0, y: 2 });
  });

  it("un 4x2 no cabe junto a un 2x2 aunque haya dos columnas libres", () => {
    expect(firstFit([placed("a")], "4x2", 4)).toEqual({ x: 0, y: 2 });
  });

  it("rellena el hueco que dejó el de en medio en vez de irse al final", () => {
    const hueco = [placed("a"), placed("c", 0, 2), placed("d", 2, 2)];

    expect(firstFit(hueco, "2x2", 4)).toEqual({ x: 2, y: 0 });
  });
});

describe("el tamaño más cercano al arrastre", () => {
  const sizes = ["2x2", "4x4"] as const;

  it("elige el declarado aunque se arrastre a uno intermedio", () => {
    expect(nearestSize([...sizes], 3, 3)).toBe("2x2");
    expect(nearestSize([...sizes], 4, 3)).toBe("4x4");
  });

  it("con un solo tamaño declarado no hay nada que elegir", () => {
    expect(nearestSize(["2x2"], 12, 12)).toBe("2x2");
  });
});

describe("el recorrido del criterio de T-031", () => {
  const inicio = (): Desk => ({
    pages: [
      {
        id: "inicio",
        items: [
          widget("por-defecto-events"),
          widget("por-defecto-entities"),
          widget("por-defecto-entities_by_volume", "4x2"),
          widget("por-defecto-sync"),
          widget("por-defecto-version"),
        ],
      },
    ],
    placements: {},
  });

  it("quitar, volver a añadir desde la hoja y agrandar deja algo distinto y válido", () => {
    const sinSync = remove(inicio(), "por-defecto-sync");
    const puesto = add(sinSync, 0, widget("nuevo-sync"));
    const grande = resize(puesto, "nuevo-sync", "4x2");

    expect(at(puesto, "mobile", 0, "nuevo-sync")).toMatchObject({ x: 2, y: 4 });
    expect(at(grande, "mobile", 0, "nuevo-sync")).toMatchObject({ size: "4x2", x: 0, y: 6 });
    expect(grande.pages[0]!.items).toHaveLength(5);
    expect(overlapping(arrangeAll(grande, "mobile")[0]!.items)).toBe(false);
  });
});

describe("cellNear", () => {
  const rect = { left: 0, top: 0, width: 388 };

  it("cae donde está la esquina de la tarjeta, no donde está el dedo", () => {
    const finger = { x: 300, y: 50 };
    const grip = { x: 300, y: 50 };
    expect(cellNear(rect, 4, 12, { x: finger.x - grip.x, y: finger.y - grip.y })).toEqual({
      x: 0,
      y: 0,
    });
  });

  it("redondea a la celda más cercana en vez de truncar", () => {
    expect(cellNear(rect, 4, 12, { x: 60, y: 140 })).toEqual({ x: 1, y: 1 });
    expect(cellNear(rect, 4, 12, { x: 40, y: 40 })).toEqual({ x: 0, y: 0 });
  });

  it("no se sale por arriba ni por los lados", () => {
    expect(cellNear(rect, 4, 12, { x: -80, y: -80 })).toEqual({ x: 0, y: 0 });
    expect(cellNear(rect, 4, 12, { x: 900, y: 0 }).x).toBe(3);
  });
});

describe("lo elegido al poner un widget (ADR-0099)", () => {
  it("no se pierde al añadirlo ni al colocarlo solo", () => {
    const desk = { pages: [{ id: "p", items: [] }], placements: {} };
    const placed = add(desk, 0, { instance_id: "a", source: "money", widget: "account", size: "2x2", option: "renault" });
    expect(placed.pages[0]?.items[0]?.option).toBe("renault");
    const arranged = arrange(placed.pages[0]!, 4);
    expect(arranged[0]?.option).toBe("renault");
  });
});
