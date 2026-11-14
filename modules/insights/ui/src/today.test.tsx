// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Fact, Onboarding, Pill, Recommendation, Settings, Tastes, Today } from "./api";
import { App } from "./App";
import { forYou, shelf } from "./Library";
import { pillState } from "./Today";
import { grouped } from "./You";

const PILL_ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const SETTINGS: Settings = {
  pill_on: true,
  pill_time: "09:00",
  pill_minutes: 15,
  pill_language: null,
  pill_level: null,
  questions: "sometimes",
  started_at: null,
};
const START: Onboarding = {
  done: false,
  answered: 0,
  total: 2,
  questions: [
    {
      id: null,
      origin: "start",
      bank_key: "start.families",
      kind: "many",
      text: "What do you like to learn about?",
      why: "So I know which topics to bring you.",
      options: [
        { value: "history", label: "History" },
        { value: "science", label: "Science and the universe" },
      ],
    },
    {
      id: null,
      origin: "start",
      bank_key: "start.time",
      kind: "one",
      text: "What time suits you?",
      why: "I let you know at that time.",
      options: [{ value: "09:00", label: "9:00" }],
    },
  ],
};
const PILL: Pill = {
  id: PILL_ID,
  day: "2026-11-10",
  origin: "daily",
  run_key: "pill:2026-11-10",
  parent_id: null,
  depth: 0,
  family_key: "history",
  topic: "The battle of Leuctra",
  hook: null,
  language: "en",
  minutes: 15,
  headline: "The column that broke Sparta",
  lead: "An army that never lost and a simple idea.",
  sections: [
    { title: "The oblique order", text: "First.\n\nSecond." },
    { title: "What came after", text: "Third." },
  ],
  to_tell: "Sparta had not lost a pitched battle in generations.",
  to_think: "Why did it take so long?",
  branches: [
    { title: "Epaminondas", why: "The general" },
    { title: "The Sacred Band", why: "150 couples" },
    { title: "The fall of Sparta", why: "From Leuctra to nothing" },
  ],
  sources: [{ title: "Battle of Leuctra", url: "https://en.wikipedia.org/wiki/Battle_of_Leuctra" }],
  glossary: [],
  reaction: null,
  read_at: "2026-11-10T09:00:00Z",
  created_at: "2026-11-10T08:40:00Z",
};
const FACT: Fact = {
  id: "f1",
  day: "2026-11-10",
  family_key: "science",
  text: "A true and surprising fact about the universe.",
  detail: null,
  source: { title: "Source", url: "https://example.org" },
  reaction: null,
  created_at: "2026-11-10T08:40:00Z",
};
const pick = (extra: Partial<Recommendation> = {}): Recommendation => ({
  id: "p1",
  kind: "book",
  list: "read",
  title: "A historical novel",
  creators: ["An author"],
  year: 2008,
  length: "720 pages",
  language: "en",
  why: "Because you liked the previous one",
  because: [],
  origin: "weekly",
  pill_id: null,
  verified: "catalog",
  links: [{ label: "Open Library", url: "https://openlibrary.org/isbn/9788466648769" }],
  state: "new",
  collections: [],
  rating: null,
  more_like: null,
  note: null,
  sent_to: null,
  has_cover: false,
  created_at: "2026-11-09T17:00:00Z",
  updated_at: "2026-11-09T17:00:00Z",
  ...extra,
});
const TASTES: Tastes = {
  traits: [
    {
      id: "t1",
      facet: "genre",
      label: "Historical novels",
      stance: 2,
      source: "seen",
      evidence: "6 novels, average 4.2",
      status: "proposed",
      updated_at: "2026-11-09T17:00:00Z",
    },
    { id: "t2", facet: "avoid", label: "Football", stance: -2, source: "said", evidence: null, status: "confirmed", updated_at: "2026-11-09T17:00:00Z" },
  ],
  families: [
    { key: "history", name: "History", hue: 3, glyph: "landmark", themes: "", weight: 2, outside: false },
    { key: "science", name: "Science and the universe", hue: 5, glyph: "atom", themes: "", weight: 1, outside: false },
  ],
  sources: [],
  settings: SETTINGS,
  onboarding: START,
};
const day = (extra: Partial<Today> = {}): Today => ({
  day: "2026-11-10",
  pill: PILL,
  asked: null,
  facts: [FACT],
  picks: [pick({ origin: "pill", pill_id: PILL_ID })],
  question: null,
  onboarding: { ...START, done: true, answered: 2, questions: [] },
  settings: SETTINGS,
  streak: 3,
  unread: 0,
  latest: null,
  waiting: [],
  ...extra,
});

let root: Root;
let host: HTMLElement;
let replies: Record<string, () => unknown>;
let asked: string[];

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;
});

beforeEach(() => {
  void reset();
  asked = [];
  replies = {
    "GET /api/insights/profile": () => ({ name: "Txuri", about: "", named: true }),
    "GET /api/insights/today": () => day(),
    "GET /api/insights/tastes": () => TASTES,
    "GET /api/insights/picks": () => [pick(), pick({ id: "p2", title: "Already saved", state: "saved" })],
    "GET /api/insights/pills": () => [],
    "GET /api/insights/onboarding": () => START,
    "GET /api/insights/version": () => ({ version: "1.1.0" }),
    [`POST /api/insights/pills/${PILL_ID}/read`]: () => PILL,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      asked.push(key);
      const reply = replies[key];
      if (!reply) return json({ detail: "not found" }, 404);
      const body = await reply();
      return body instanceof Response ? body : json(body);
    }),
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const retry = () => host.querySelector<HTMLButtonElement>(".empty-state[role=alert] button") ?? undefined;

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path: string) {
  window.history.replaceState(null, "", path);
  act(() => root.render(<App />));
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("what is decided without drawing", () => {
  it("what to say of the pill that is not there yet", () => {
    expect(pillState(day())).toBe("ready");
    expect(pillState(day({ pill: null }))).toBe("later");
    expect(pillState(day({ pill: null, settings: { ...SETTINGS, pill_on: false } }))).toBe("off");
    const waiting = { id: "a", kind: "pill", key: "pill:x", origin: "daily", parent_id: null, branch: null, family_key: null, asked_at: "", detail: null, pill_id: null } as const;
    expect(pillState(day({ pill: null, asked: { ...waiting, state: "waiting" } }))).toBe("writing");
    expect(pillState(day({ pill: null, asked: { ...waiting, state: "failed" } }))).toBe("failed");
  });

  it("the library: what is unopened on top and each list, what is done at the end", () => {
    const all = [
      pick({ id: "a", state: "done", updated_at: "2026-11-10" }),
      pick({ id: "b", state: "doing" }),
      pick({ id: "c", state: "new" }),
      pick({ id: "d", state: "saved", list: "watch", kind: "film" }),
    ];
    expect(shelf(all, "read", false).map((one) => one.id)).toEqual(["b", "a"]);
    expect(shelf(all, "read", true).map((one) => one.id)).toEqual(["b"]);
    expect(forYou(all).map((one) => one.id)).toEqual(["c"]);
  });

  it("what is confirmed by facet, without what is proposed or dismissed", () => {
    expect(grouped(TASTES.traits).map((group) => [group.facet, group.traits.length])).toEqual([["avoid", 1]]);
  });
});

describe("today", () => {
  it("the whole pill, with its bar, its facts, its branches and what to follow", async () => {
    await open("/insights/");

    expect(host.textContent).toContain("Your pill");
    expect(host.textContent).toContain("The column that broke Sparta");
    expect(host.textContent).toContain("To tell");
    expect(host.textContent).toContain("Today's facts");
    expect(host.textContent).toContain("I want to know more about…");
    expect(host.textContent).toContain("To follow");
    expect(host.querySelector('[aria-label="Parts of the pill"]')).not.toBeNull();
    expect(host.textContent).toContain("Talk to Txuri");
    expect(await serious()).toEqual([]);
  });

  it("before its time it says when it arrives and it can be asked for now", async () => {
    replies["GET /api/insights/today"] = () => day({ pill: null, facts: [], picks: [] });
    replies["POST /api/insights/pills/more"] = () => ({
      id: "a1",
      kind: "more",
      key: "more:x",
      origin: "surprise",
      parent_id: null,
      branch: null,
      family_key: "science",
      asked_at: "2026-11-10T08:00:00Z",
      state: "waiting",
      detail: null,
      pill_id: null,
    });
    await open("/insights/");
    expect(host.textContent).toContain("Your pill arrives at 09:00");

    act(() => button("Ask for it now")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/pills/more");
    expect(host.textContent).toContain("is writing another pill");
  });

  it("the Insights question is answered with one tap", async () => {
    replies["GET /api/insights/today"] = () =>
      day({
        question: {
          id: "q1",
          origin: "pass",
          bank_key: null,
          kind: "either",
          text: "Sagas or self-contained novels?",
          why: "You finished several sagas",
          options: [
            { value: "saga", label: "Sagas" },
            { value: "one", label: "Self-contained" },
          ],
        },
      });
    replies["POST /api/insights/questions/q1/answer"] = () => ({});
    await open("/insights/");
    expect(host.textContent).toContain("Txuri asks you");

    act(() => button("Sagas")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/questions/q1/answer");
  });

  it("the first time it invites to let it get to know you", async () => {
    replies["GET /api/insights/today"] = () => day({ onboarding: START, pill: null });
    await open("/insights/");
    act(() => button("Start")!.click());
    await settle();
    expect(window.location.pathname).toBe("/insights/start");
  });

  it("if it fails, retry", async () => {
    replies["GET /api/insights/today"] = () => json({ detail: "no" }, 500);
    await open("/insights/");
    expect(host.textContent).toContain("Your day could not be opened");

    replies["GET /api/insights/today"] = () => day();
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("The column that broke Sparta");
  });
});

describe("the library", () => {
  it("this week's in cards, and saving moves it to the list", async () => {
    replies["POST /api/insights/picks/p1/save"] = () => pick({ state: "saved", sent_to: "library" });
    await open("/insights/library");
    expect(host.textContent).toContain("For you this week");
    expect(host.textContent).toContain("Because you liked the previous one");
    expect(host.textContent).toContain("Already saved");

    act(() => button("Save")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/picks/p1/save");
    expect(await serious()).toEqual([]);
  });

  it("with nothing, it says how things arrive", async () => {
    replies["GET /api/insights/picks"] = () => [];
    await open("/insights/library");
    expect(host.textContent).toContain("Nothing saved here yet");
  });
});

describe("you", () => {
  it("what is proposed is confirmed, and what it knows shows where it comes from", async () => {
    replies["PUT /api/insights/traits/t1"] = () => ({ ...TASTES.traits[0], status: "confirmed" });
    await open("/insights/you");
    expect(host.textContent).toContain("Is it so?");
    expect(host.textContent).toContain("6 novels, average 4.2");
    expect(host.textContent).toContain("Football");
    expect(host.textContent).toContain("Your topics");

    act(() => (host.querySelector('[aria-label$=": Historical novels"]') as HTMLButtonElement).click());
    await settle();
    expect(asked).toContain("PUT /api/insights/traits/t1");
    expect(await serious()).toEqual([]);
  });

  it("getting to know you, one question at a time", async () => {
    replies["POST /api/insights/onboarding/start.families"] = () => ({ ...START, answered: 1, questions: START.questions.slice(1) });
    await open("/insights/start");
    expect(host.textContent).toContain("What do you like to learn about?");
    expect(host.textContent).toContain("1 de 2");

    act(() => button("History")!.click());
    act(() => button("Seguir")!.click());
    await settle();
    expect(asked).toContain("POST /api/insights/onboarding/start.families");
    expect(host.textContent).toContain("What time suits you?");
    expect(await serious()).toEqual([]);
  });
});
