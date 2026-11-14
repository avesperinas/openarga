import { renderToString } from "react-dom/server";

import { route } from "./App";
import type { Figure, Insight, LastRun } from "./api";
import { InboxScreen, sections } from "./Inbox";
import { amount, lastLook, paragraphs, versus, when } from "./words";
import { PATIENCE_MS, sends, stale, thinkingFor, threadLine } from "./Chat";

const figure = (extra: Partial<Figure> = {}): Figure => ({
  label: "restaurant spending",
  value: 412,
  unit: "€",
  baseline: 258,
  baseline_label: "your 12-month average",
  ...extra,
});

const insight = (id: string, read: boolean): Insight => ({
  id,
  kind: "alert",
  domain: "money",
  topic: "money.spend:restaurants",
  title: id,
  body: "text",
  figures: [figure()],
  affects: "the cushion",
  action: "Two fewer dinners out this month",
  created_at: "2026-10-08T07:00:00Z",
  read_at: read ? "2026-10-08T08:00:00Z" : null,
  rating: null,
  rated_at: null,
});

test("each figure says how far it is from your usual", () => {
  expect(versus(figure())).toBe("+60 % against 258 €, your 12-month average");
  expect(versus(figure({ value: 6.1, baseline: 7.2, unit: "h", baseline_label: "your average" }))).toBe(
    "−15 % against 7.2 h, your average",
  );
  expect(amount(8400, "steps")).toBe("8,400 steps");
});

test("what is unread goes on top, and an empty section is not drawn", () => {
  const found = sections([insight("a", true), insight("b", false), insight("c", true)]);

  expect(found.map((one) => [one.title, one.insights.map((i) => i.id)])).toEqual([
    ["Unread", ["b"]],
    ["Read", ["a", "c"]],
  ]);
  expect(sections([insight("a", true)]).map((one) => one.title)).toEqual(["Read"]);
});

test("each section, piece of advice and pill has its address", () => {
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

test("today, yesterday and the day", () => {
  const now = new Date("2026-10-08T12:00:00");
  expect(when("2026-10-08T07:00:00", now)).toBe("today");
  expect(when("2026-10-07T23:00:00", now)).toBe("yesterday");
  expect(when("2026-10-01T10:00:00", now)).toBe("Thursday 1 October");
});

test("paragraphs are separated by a blank line", () => {
  expect(paragraphs("Uno.\n\nDos\nsigue.\n\n\n")).toEqual(["Uno.", "Dos\nsigue."]);
});

test("the inbox draws without breaking before it has data", () => {

  expect(renderToString(<InboxScreen onOpen={() => undefined} onSettings={() => undefined} />)).toContain("Advice");
});

test("a conversation says whether it waits, failed or when it was", () => {
  const base = { id: "t", title: "x", insight_id: null, created_at: "2026-10-08T07:00:00Z", updated_at: new Date().toISOString() };

  expect(threadLine({ ...base, waiting_since: "2026-10-08T07:00:00Z", problem: null }, "Txuri")).toBe("Txuri is thinking…");
  expect(threadLine({ ...base, waiting_since: null, problem: "not allowed" }, "Txuri")).toBe("It could not answer");
  expect(threadLine({ ...base, waiting_since: null, problem: null }, "Txuri")).toBe("today");
  const now = Date.parse("2026-10-08T07:00:00Z");
  expect(stale({ waiting_since: "2026-10-08T07:00:00Z" }, now + PATIENCE_MS + 1)).toBe(true);
  expect(stale({ waiting_since: "2026-10-08T07:00:00Z" }, now + 1000)).toBe(false);
});

test("how long it has been thinking, in seconds and then minutes", () => {
  const since = "2026-10-08T07:00:00Z";
  const at = (seconds: number) => Date.parse(since) + seconds * 1000;

  expect(thinkingFor(since, at(8))).toBe("8 s");
  expect(thinkingFor(since, at(65))).toBe("1 min 5 s");
  expect(thinkingFor(since, at(120))).toBe("2 min");
});

test("Enter sends and Shift+Enter does not; nor while an accent is composed", () => {
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

test("it says when it last looked and what happened", () => {
  const now = new Date("2026-10-13T12:00:00Z");

  expect(lastLook([], "Txuri", now)).toBe(
    "Txuri looks at your data every morning from seven and gives you the summary on Sunday.",
  );
  expect(lastLook([run()], "Txuri", now)).toMatch(/^It looked today at \d\d:00: nothing new/);
  expect(lastLook([run({ state: "waiting" })], "Txuri", now)).toMatch(/is running/);
  expect(lastLook([run({ state: "refused", detail: "Insights is not allowed." })], "Txuri", now)).toBe(
    "Insights is not allowed.",
  );
  expect(lastLook([run(), run({ kind: "weekly", asked_at: "2026-10-13T08:00:00Z", state: "error", detail: "Cut off" })], "Txuri", now)).toMatch(
    /^The week's summary of today at \d\d:00 did not come out: Cut off$/,
  );
});

test("it says what it ran with and what happens if it did not come out", () => {
  const now = new Date("2026-10-13T12:00:00Z");

  expect(lastLook([run({ state: "ok", ran_with: "Other" })], "Txuri", now)).toMatch(
    /with “Other”/,
  );
  expect(
    lastLook(
      [run({ state: "skipped", detail: "No room", fix: "It will be asked again on its own." })],
      "Txuri",
      now,
    ),
  ).toMatch(/did not come out: No room It will be asked again on its own\.$/);
});

describe("the inbox, with the figure that says it (T-B22)", () => {
  it("the change alone, where it comes from and the figure in one line", async () => {
    const { changeOf, against } = await import("./words");
    const { origin, headline } = await import("./Inbox");
    const figure = { label: "Sleep", value: 6.2, unit: "h", baseline: 7.25, baseline_label: "your average" };
    expect(changeOf(figure)).toBe("−14 %");
    expect(changeOf({ ...figure, baseline: 0 })).toBeNull();
    expect(against(figure)).toBe("against 7.3 h, your average");
    const insight = {
      kind: "alert",
      domain: "body",
      created_at: new Date().toISOString(),
      figures: [figure],
    } as never;
    expect(origin(insight)).toBe("Body · today");
    expect(headline(insight)).toBe("Sleep 6.2 h · −14 %");
    expect(headline({ ...(insight as object), figures: [] } as never)).toBeNull();
  });
});

describe("the pill read aloud (ADR-0182)", () => {
  it("with a voice, the server audio and its timeline; without it, the device's", async () => {
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
