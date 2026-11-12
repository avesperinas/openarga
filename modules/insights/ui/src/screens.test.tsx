import { renderToString } from "react-dom/server";

import { route } from "./App";
import type { Figure, Insight, LastRun } from "./api";
import { InboxScreen, sections } from "./Inbox";
import { amount, lastLook, paragraphs, versus, when } from "./words";
import { PATIENCE_MS, sends, stale, thinkingFor, threadLine } from "./Chat";

const figure = (extra: Partial<Figure> = {}): Figure => ({
  label: "gasto en restaurantes",
  value: 412,
  unit: "€",
  baseline: 258,
  baseline_label: "tu media de 12 meses",
  ...extra,
});

const insight = (id: string, read: boolean): Insight => ({
  id,
  kind: "alert",
  domain: "money",
  topic: "money.gasto:restaurantes",
  title: id,
  body: "texto",
  figures: [figure()],
  affects: "el colchón",
  action: "Dos cenas fuera menos este mes",
  created_at: "2026-10-08T07:00:00Z",
  read_at: read ? "2026-10-08T08:00:00Z" : null,
  rating: null,
  rated_at: null,
});

test("cada cifra dice cuánto se separa de lo tuyo", () => {
  expect(versus(figure())).toBe("+60 % frente a 258 €, tu media de 12 meses");
  expect(versus(figure({ value: 6.1, baseline: 7.2, unit: "h", baseline_label: "tu media" }))).toBe(
    "−15 % frente a 7,2 h, tu media",
  );
  expect(amount(8400, "pasos")).toBe("8400 pasos");
});

test("lo no leído va arriba, y una sección vacía no se pinta", () => {
  const found = sections([insight("a", true), insight("b", false), insight("c", true)]);

  expect(found.map((one) => [one.title, one.insights.map((i) => i.id)])).toEqual([
    ["Sin leer", ["b"]],
    ["Leídos", ["a", "c"]],
  ]);
  expect(sections([insight("a", true)]).map((one) => one.title)).toEqual(["Leídos"]);
});

test("cada sección, cada consejo y cada píldora tienen su dirección", () => {
  expect(route("/insights/")).toEqual({ tab: "today", pill: null });
  expect(route("/insights/pildora/0a0a0a0a-0000-4000-8000-00000000a0a0")).toEqual({
    tab: "today",
    pill: "0a0a0a0a-0000-4000-8000-00000000a0a0",
  });
  expect(route("/insights/consejos")).toEqual({ tab: "inbox", insight: null });
  expect(route("/insights/biblioteca")).toEqual({ tab: "library" });
  expect(route("/insights/tu")).toEqual({ tab: "you", start: false });
  expect(route("/insights/conocerte")).toEqual({ tab: "you", start: true });
  expect(route("/insights/consejo/0a0a0a0a-0000-4000-8000-00000000a0a0")).toEqual({
    tab: "inbox",
    insight: "0a0a0a0a-0000-4000-8000-00000000a0a0",
  });
  expect(route("/insights/ajustes")).toEqual({ tab: "settings" });
  expect(route("/insights/hablar")).toEqual({ tab: "chat", thread: null, fresh: false });
  expect(route("/insights/hablar/nueva")).toEqual({ tab: "chat", thread: null, fresh: true });
  expect(route("/insights/hablar/0a0a0a0a-0000-4000-8000-00000000a0a0")).toEqual({
    tab: "chat",
    thread: "0a0a0a0a-0000-4000-8000-00000000a0a0",
    fresh: false,
  });
});

test("hoy, ayer y el día", () => {
  const now = new Date("2026-10-08T12:00:00");
  expect(when("2026-10-08T07:00:00", now)).toBe("hoy");
  expect(when("2026-10-07T23:00:00", now)).toBe("ayer");
  expect(when("2026-10-01T10:00:00", now)).toBe("jueves, 1 de octubre");
});

test("los párrafos se separan por una línea en blanco", () => {
  expect(paragraphs("Uno.\n\nDos\nsigue.\n\n\n")).toEqual(["Uno.", "Dos\nsigue."]);
});

test("la bandeja se pinta sin romperse antes de tener datos", () => {

  expect(renderToString(<InboxScreen onOpen={() => undefined} onSettings={() => undefined} />)).toContain("Consejos");
});

test("una conversación dice si espera, si falló o cuándo fue", () => {
  const base = { id: "t", title: "x", insight_id: null, created_at: "2026-10-08T07:00:00Z", updated_at: new Date().toISOString() };

  expect(threadLine({ ...base, waiting_since: "2026-10-08T07:00:00Z", problem: null }, "Txuri")).toBe("Txuri está pensando…");
  expect(threadLine({ ...base, waiting_since: null, problem: "sin permiso" }, "Txuri")).toBe("No ha podido contestar");
  expect(threadLine({ ...base, waiting_since: null, problem: null }, "Txuri")).toBe("hoy");
  const now = Date.parse("2026-10-08T07:00:00Z");
  expect(stale({ waiting_since: "2026-10-08T07:00:00Z" }, now + PATIENCE_MS + 1)).toBe(true);
  expect(stale({ waiting_since: "2026-10-08T07:00:00Z" }, now + 1000)).toBe(false);
});

test("cuánto lleva pensando, en segundos y luego en minutos", () => {
  const since = "2026-10-08T07:00:00Z";
  const at = (seconds: number) => Date.parse(since) + seconds * 1000;

  expect(thinkingFor(since, at(8))).toBe("8 s");
  expect(thinkingFor(since, at(65))).toBe("1 min 5 s");
  expect(thinkingFor(since, at(120))).toBe("2 min");
});

test("Enter envía y Mayúsculas+Enter no; tampoco mientras se compone un acento", () => {
  const key = (shiftKey: boolean, isComposing = false) =>
    ({ key: "Enter", shiftKey, nativeEvent: { isComposing } }) as never;

  expect(sends(key(false))).toBe(true);
  expect(sends(key(true))).toBe(false);
  expect(sends(key(false, true))).toBe(false);
  expect(sends({ key: "a", shiftKey: false, nativeEvent: {} } as never)).toBe(false);
});

const run = (extra: Partial<LastRun> = {}): LastRun => ({
  kind: "morning",
  key: "morning:2026-10-13",
  asked_at: "2026-10-13T06:00:00Z",
  signals: 0,
  state: "quiet",
  detail: null,
  ...extra,
});

test("dice cuándo miró por última vez y qué pasó", () => {
  const now = new Date("2026-10-13T12:00:00Z");

  expect(lastLook([], "Txuri", now)).toBe(
    "Txuri mira tus datos cada mañana desde las siete y el domingo te hace el resumen.",
  );
  expect(lastLook([run()], "Txuri", now)).toMatch(/^Miró hoy a las \d\d:00: nada nuevo/);
  expect(lastLook([run({ state: "waiting" })], "Txuri", now)).toMatch(/está en marcha/);
  expect(lastLook([run({ state: "refused", detail: "Insights no tiene permiso." })], "Txuri", now)).toBe(
    "Insights no tiene permiso.",
  );
  expect(lastLook([run(), run({ kind: "weekly", asked_at: "2026-10-13T08:00:00Z", state: "error", detail: "Cortada" })], "Txuri", now)).toMatch(
    /^El resumen de la semana de hoy a las \d\d:00 no salió: Cortada$/,
  );
});

test("dice con qué cuenta miró y qué va a pasar si no salió", () => {
  const now = new Date("2026-10-13T12:00:00Z");

  expect(lastLook([run({ state: "ok", ran_with: "Otra" })], "Txuri", now)).toMatch(
    /con tu cuenta «Otra», porque la de siempre no podía/,
  );
  expect(
    lastLook(
      [run({ state: "skipped", detail: "Sin hueco", fix: "Tus cuentas de Claude van sin hueco: se vuelve a pedir sola." })],
      "Txuri",
      now,
    ),
  ).toMatch(/no salió: Sin hueco Tus cuentas de Claude van sin hueco: se vuelve a pedir sola\.$/);
});

describe("la bandeja, con la cifra que lo dice (T-B22)", () => {
  it("el cambio solo, de dónde viene y la cifra en una línea", async () => {
    const { changeOf, against } = await import("./words");
    const { origin, headline } = await import("./Inbox");
    const figure = { label: "Sueño", value: 6.2, unit: "h", baseline: 7.25, baseline_label: "tu media" };
    expect(changeOf(figure)).toBe("−14 %");
    expect(changeOf({ ...figure, baseline: 0 })).toBeNull();
    expect(against(figure)).toBe("frente a 7,3 h, tu media");
    const insight = {
      kind: "alert",
      domain: "body",
      created_at: new Date().toISOString(),
      figures: [figure],
    } as never;
    expect(origin(insight)).toBe("Cuerpo · hoy");
    expect(headline(insight)).toBe("Sueño 6,2 h · −14 %");
    expect(headline({ ...(insight as object), figures: [] } as never)).toBeNull();
  });
});

describe("la píldora en voz alta (ADR-0182)", () => {
  it("con voz, el audio del servidor y su línea de tiempo; sin ella, la del dispositivo", async () => {
    const { audioOf } = await import("./api");
    const base = { id: "0a0a0a0a-0000-4000-8000-00000000a0a0" } as Parameters<typeof audioOf>[0];
    expect(audioOf({ ...base, audio: { duration: 90, timeline: [0, 4] } })).toEqual({
      src: "/api/insights/pills/0a0a0a0a-0000-4000-8000-00000000a0a0/audio",
      duration: 90,
      timeline: [0, 4],
    });
    expect(audioOf({ ...base, audio: null })).toBeNull();
    expect(audioOf(base)).toBeNull();
  });
});
