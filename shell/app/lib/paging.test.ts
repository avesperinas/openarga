import { describe, expect, it } from "vitest";

import { WHEEL_QUIET_MS, clampPage, keyDirection, groupPages, pairStart, positionOf, trackHeight, wheelPager } from "./paging";

describe("wheelPager", () => {
  it("un clic de rueda pasa una pantalla", () => {
    const pager = wheelPager();
    expect(pager(100, 0, 0)).toBe(1);
  });

  it("hacia arriba vuelve atrás", () => {
    const pager = wheelPager();
    expect(pager(-100, 0, 0)).toBe(-1);
  });

  it("un roce de trackpad no cambia de pantalla", () => {
    const pager = wheelPager();
    expect(pager(4, 0, 0)).toBe(0);
    expect(pager(6, 0, 16)).toBe(0);
  });

  it("un gesto de trackpad con inercia pasa una sola pantalla", () => {
    const pager = wheelPager();
    const steps = Array.from({ length: 60 }, (_, frame) => pager(12, 0, frame * 16));
    expect(steps.filter((step) => step !== 0)).toEqual([1]);
  });

  it("después de un silencio, el siguiente gesto vuelve a contar", () => {
    const pager = wheelPager();
    expect(pager(100, 0, 0)).toBe(1);
    expect(pager(100, 0, 50)).toBe(0);
    expect(pager(100, 0, 50 + WHEEL_QUIET_MS + 1)).toBe(1);
  });

  it("en Firefox la rueda llega en líneas y también pasa", () => {
    const pager = wheelPager();
    expect(pager(3, 1, 0)).toBe(1);
  });
});

describe("keyDirection", () => {
  it("solo las flechas laterales mueven de pantalla", () => {
    expect(keyDirection("ArrowLeft")).toBe(-1);
    expect(keyDirection("ArrowRight")).toBe(1);
    expect(keyDirection("ArrowDown")).toBe(0);
    expect(keyDirection("a")).toBe(0);
  });
});

describe("clampPage", () => {
  it("no se sale por ninguno de los dos extremos", () => {
    expect(clampPage(-1, 3)).toBe(0);
    expect(clampPage(3, 3)).toBe(2);
    expect(clampPage(1, 3)).toBe(1);
  });
});

describe("trackHeight", () => {
  const heights = [400, 1200, 200];

  it("en reposo es el alto de la pantalla que se mira, no el de la más alta", () => {
    expect(trackHeight(heights, 0, 390)).toBe(400);
    expect(trackHeight(heights, 780, 390)).toBe(200);
  });

  it("a medio deslizar no cambia: ni encoge bajo el dedo ni crece y hace a Safari reencajar", () => {
    expect(trackHeight(heights, 30, 390)).toBeNull();
    expect(trackHeight(heights, 195, 390)).toBeNull();
    expect(trackHeight(heights, 760, 390)).toBeNull();
  });

  it("al encajar, aunque sea a medio píxel, es el de la pantalla que queda", () => {
    expect(trackHeight(heights, 389.6, 390)).toBe(1200);
    expect(trackHeight(heights, 780.4, 390)).toBe(200);
  });

  it("no se sale por los extremos ni divide entre cero", () => {
    expect(trackHeight(heights, 5000, 390)).toBe(200);
    expect(trackHeight(heights, -20, 390)).toBe(400);
    expect(trackHeight(heights, 100, 0)).toBe(400);
    expect(trackHeight([], 0, 390)).toBe(0);
  });
});

describe("de dos en dos en una pantalla ancha", () => {
  it("con una a la vez, cada pantalla es la suya", () => {
    expect(pairStart(3, 4, 1)).toBe(3);
  });

  it("de dos en dos, se va a la primera de su pareja", () => {
    expect([0, 1, 2, 3].map((index) => pairStart(index, 4, 2))).toEqual([0, 0, 2, 2]);
  });

  it("con un número impar, la última va sola", () => {
    expect([0, 1, 2, 3, 4].map((index) => pairStart(index, 5, 2))).toEqual([0, 0, 2, 2, 4]);
  });

  it("con menos pantallas que las que caben, la primera", () => {
    expect(pairStart(0, 1, 2)).toBe(0);
  });
});

describe("por qué pantalla va el carril", () => {
  it("con pantallas de anchos distintos, en el inicio de cada una cuenta entera", () => {
    const offsets = [0, 400, 1700, 2100];
    expect(offsets.map((left) => positionOf(offsets, left))).toEqual([0, 1, 2, 3]);
  });

  it("entre dos, la parte recorrida de la que se deja", () => {
    expect(positionOf([0, 400, 1700], 1050)).toBe(1.5);
  });

  it("fuera de los extremos, la primera o la última", () => {
    expect(positionOf([0, 400], -20)).toBe(0);
    expect(positionOf([0, 400], 900)).toBe(1);
  });
});

describe("las pantallas que se ven a la vez en un ordenador ancho", () => {
  it("cuatro pantallas de un panel, juntas; la quinta empieza otro grupo", () => {
    const spans = groupPages([4, 4, 4, 4, 4]);
    expect(spans.map((span) => span.start)).toEqual([0, 0, 0, 0, 4]);
    expect(spans.map((span) => span.edge)).toEqual(["start", "middle", "middle", "end", "only"]);
    expect(spans[0]!.group).toBe(16);
  });

  it("una de doce columnas va con una de cuatro, y dos de doce van solas", () => {
    expect(groupPages([12, 4, 12, 12]).map((span) => span.start)).toEqual([0, 0, 2, 3]);
  });
});
