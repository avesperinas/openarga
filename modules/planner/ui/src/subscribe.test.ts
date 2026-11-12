import { describe, expect, test } from "vitest";

import { statusLine } from "./Subscribe";

const NOW = new Date("2026-09-28T12:00:00Z").getTime();
const state = (over: Record<string, unknown>) => ({
  subscription: { provider: "ical", updated_at: null, failing: false, detail: null, paused: false, ...over },
});

describe("cómo va una suscripción", () => {
  test("hasta la primera pasada, se espera", () => {
    expect(statusLine({ subscription: null }, NOW)).toBe("Esperando la primera pasada");
    expect(statusLine(state({}), NOW)).toBe("Esperando la primera pasada");
  });

  test("la edad de lo que se ve", () => {
    expect(statusLine(state({ updated_at: "2026-09-28T11:59:40Z" }), NOW)).toBe("Actualizada ahora");
    expect(statusLine(state({ updated_at: "2026-09-28T11:35:00Z" }), NOW)).toBe("Actualizada hace 25 min");
    expect(statusLine(state({ updated_at: "2026-09-28T09:00:00Z" }), NOW)).toBe("Actualizada hace 3 h");
    expect(statusLine(state({ updated_at: "2026-09-24T12:00:00Z" }), NOW)).toBe("Actualizada hace 4 días");
  });

  test("si falla, con las palabras de la fuente; en pausa, se dice", () => {
    expect(statusLine(state({ updated_at: "2026-09-28T09:00:00Z", failing: true, detail: "no contesta" }), NOW)).toBe(
      "Falla: no contesta",
    );
    expect(statusLine(state({ paused: true }), NOW)).toBe("En pausa en Hub");
  });
});
