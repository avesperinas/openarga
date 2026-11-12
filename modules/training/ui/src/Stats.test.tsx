import { remember, reset } from "@openarga/app";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Machine, MuscleSummary, Stats, VariantPoint } from "./api";
import { ExerciseSummary, StatsScreen, VolumeCard, exerciseLabel, periodLabel, signed, sparkline, whyNot } from "./Stats";

describe("cómo se leen los números de Stats", () => {
  it("el signo va en el texto, no solo en el color", () => {
    expect(signed(2.1)).toBe("+2,1 %");
    expect(signed(-2.1)).toBe("−2,1 %");
    expect(signed(0)).toBe("+0,0 %");
  });

  it("la coma decimal es la de aquí", () => {
    expect(signed(12.35)).toContain(",");
    expect(signed(12.35)).not.toContain(".");
  });

  it("cada periodo tiene su nombre escrito", () => {
    expect(periodLabel("4w")).toBe("4 semanas");
    expect(periodLabel("all")).toBe("Desde el principio");
  });
});

describe("la línea del índice", () => {
  const coords = (values: number[]): { x: number; y: number }[] =>
    sparkline(values)
      .split(" ")
      .filter(Boolean)
      .map((pair) => {
        const [x, y] = pair.split(",").map(Number);
        return { x: x ?? 0, y: y ?? 0 };
      });

  it("empieza a la izquierda y acaba a la derecha, dentro de la caja", () => {
    const points = coords([100, 102, 104]);

    expect(points).toHaveLength(3);
    expect(points[0]?.x).toBe(0);
    expect(points[2]?.x).toBe(320);
    expect(points.every((point) => point.y >= 0 && point.y <= 64)).toBe(true);
  });

  it("lo más alto se pinta arriba", () => {
    const points = coords([100, 101, 105]);

    expect(points[2]?.y).toBeLessThan(points[0]?.y ?? 0);
  });

  it("una línea plana no se sale de la caja", () => {
    const points = coords([100, 100, 100]);

    expect(points.every((point) => Number.isFinite(point.y) && point.y >= 0 && point.y <= 64)).toBe(
      true,
    );
  });

  it("con un solo punto no hay línea que dibujar", () => {
    expect(sparkline([100])).toBe("");
  });
});

describe("cómo se nombra y se explica", () => {
  it("una variante que ya lleva el ejercicio en el nombre no lo repite", () => {
    expect(exerciseLabel({ exercise: "Press banca", variant: "Press banca con barra" })).toBe("Press banca con barra");
    expect(exerciseLabel({ exercise: "Jalón", variant: "Polea alta" })).toBe("Jalón · Polea alta");
  });

  const point: VariantPoint = {
    id: "p",
    session_id: "s",
    day: "2025-04-02",
    reps: 3,
    load: 140,
    e1rm: 154,
    reliable: true,
    status: "high",
    reference: 115.5,
    verdict: null,
  };

  it("un día apartado dice cuánto se aleja y de qué", () => {
    expect(whyNot(point)).toBe(
      "Un 33 % por encima de las sesiones de alrededor en esta máquina (lo habitual, 115,5 kg)",
    );
    expect(whyNot({ ...point, status: "excluded", verdict: "excluded" })).toBe("Lo apartaste tú");
    expect(whyNot({ ...point, status: "counted", verdict: "counted" })).toBe("Cuenta porque lo dijiste tú");
    expect(whyNot({ ...point, status: "counted" })).toBeNull();
  });
});

describe("la tarjeta de músculos", () => {
  const muscle = (id: string, name: string, region: string, delta: number | null): MuscleSummary => ({
    muscle: id,
    name,
    region,
    sets: delta === null ? 0 : 12,
    band: delta === null ? "low" : "ok",
    value: delta === null ? null : 100 + delta,
    delta,
    direction: delta === null ? null : delta > 1 ? "up" : delta < -1 ? "down" : "flat",
    trend: [],
    last_day: null,
    current: null,
    excluded: 0,
  });
  const stats = (bodyweight: number | null): Stats => ({
    period: "3m",
    since: "2026-06-24",
    until: "2026-09-23",
    sessions: 30,
    index: { value: 102, delta: 2, direction: "up", muscles: 1, trend: [] },
    frequency: { done: 2, goal: 5, average: 4, streak: 0 },
    muscles: [muscle("chest", "Pecho", "upper", 4.2), muscle("calves", "Gemelo", "lower", null)],
    movers: [],
    excluded: 0,
    bodyweight,
  });

  it("enseña todos los grupos, también los que no tienen datos de fuerza", () => {
    const html = renderToString(<VolumeCard stats={stats(80)} onOpen={() => undefined} />).replaceAll("<!-- -->", "");

    expect(html).toContain("Pecho");
    expect(html).toContain("+4,2 %");
    expect(html).toContain("Gemelo");
    expect(html).toContain("Tren inferior");
    expect(html).not.toContain("Sin tu peso");
  });

  it("pinta el cuerpo de frente y de espalda, cada músculo un botón con su nombre (T-B05)", () => {
    const html = renderToString(<VolumeCard stats={stats(80)} onOpen={() => undefined} />);

    expect(html).toContain('aria-label="Fuerza por músculo en el periodo, de frente"');
    expect(html).toContain('aria-label="Fuerza por músculo en el periodo, de espalda"');
    expect(html).toMatch(/data-muscle="chest"[^>]*role="button"[^>]*aria-label="Pecho"/);
    expect(html).toContain("var(--positive)");
  });

  it("sin peso corporal avisa de que dominadas y fondos no cuentan", () => {
    const html = renderToString(<VolumeCard stats={stats(null)} onOpen={() => undefined} />);

    expect(html).toContain("Sin tu peso");
  });

  it("se pinta al momento con lo último que se vio, sin esperar a la red (T-B10)", async () => {
    await reset();
    remember("stats:3m", stats(80));

    const html = renderToString(<StatsScreen />).replaceAll("<!-- -->", "");

    expect(html).toContain("Pecho");
    expect(html).not.toContain('aria-busy="true"');
    await reset();
  });

  it("la pantalla va en secciones, con el cuerpo primero (T-B05)", () => {
    const html = renderToString(<StatsScreen initial={stats(80)} />).replaceAll("<!-- -->", "");
    const titles = [...html.matchAll(/<h2 class="section-title">([^<]+)</g)].map((match) => match[1]);

    expect(titles).toEqual(["Músculos", "Rendimiento", "Constancia"]);
  });
});

describe("un ejercicio (T-B05)", () => {
  const point = (id: string, day: string, e1rm: number): VariantPoint => ({
    id,
    session_id: `s-${id}`,
    day,
    reps: 5,
    load: Math.round((e1rm / (1 + 5 / 30)) * 10) / 10,
    e1rm,
    reliable: true,
    status: "counted",
    reference: null,
    verdict: null,
  });
  const points = [
    point("1", "2026-07-01", 100),
    point("2", "2026-07-08", 102),
    point("3", "2026-07-15", 101),
    point("4", "2026-07-22", 104),
    point("5", "2026-07-29", 106),
  ];
  const machine: Machine = {
    gym_id: "g",
    gym: "Centro",
    first_day: "2026-07-01",
    last_day: "2026-07-29",
    points,
    segments: [],
    marks: [],
    best: points[4]!,
    records: [
      { range: "1-5", load: 90.9, reps: 5, day: "2026-07-29", reliable: true },
      { range: "11+", load: 60, reps: 12, day: "2026-07-08", reliable: false },
    ],
    without_pr: 0,
    excluded: 0,
  };
  const html = renderToString(<ExerciseSummary machine={machine} increment={2.5} external period="3m" />).replaceAll(
    "<!-- -->",
    "",
  );

  it("dice el máximo estimado y cuánto cambió en el periodo", () => {
    expect(html).toContain("106<span");
    expect(html).toContain("+6 kg en 3 meses");
  });

  it("la línea marca los récords y sombrea el rango normal", () => {
    expect(html.match(/data-highlight=""/g)).toHaveLength(3);
    expect(html).toContain("trend-chart-band");
    expect(html).toContain("Tu rango normal");
  });

  it("dice qué hacer la próxima vez", () => {
    expect(html).toContain("Dos sesiones seguidas con récord.");
    expect(html).toContain("Para un récord la próxima vez: 5 × 92,5 kg.");
  });

  it("los récords por repeticiones, con lo poco fiable apagado", () => {
    expect(html).toContain("Récord por repeticiones");
    expect(html).toContain('<div data-muted=""><dt>11+ reps</dt>');
  });
});
