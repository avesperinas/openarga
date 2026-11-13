import { describe, expect, it } from "vitest";

import type { Layer, Occurrence } from "./api";
import { counts, duplicatesOf, shortName, sidebarGroups, similar, toGridEvent } from "./data";

const layer = (origin: Layer["origin"]): Layer => ({
  id: "l1",
  name: "Training",
  tone: 3,
  origin,
  visible: true,
  position: 0,
  connection_id: null,
  app: origin === "app" ? "training" : null,
});

const occurrence: Occurrence = {
  id: "app:1",
  event_id: "app:1",
  calendar_id: "l1",
  title: "Torso",
  all_day: false,
  start: "2026-10-06T18:00:00+02:00",
  end: "2026-10-06T19:00:00+02:00",
  tz: "Europe/Madrid",
  location: null,
  notes: null,
  url: null,
  status: "confirmed",
  original_start: null,
  rrule: null,
  repeat: null,
  moved: false,
  href: "/training/sesion/1",
};

describe("what comes from another app", () => {
  it("cannot be dragged if its app does not allow moving it from here", () => {
    const event = toGridEvent(occurrence, layer("app"));

    expect(event.readOnly).toBe(true);
    expect(event.subscribed).toBe(false);
  });

  it("can be dragged if its app moves it (ADR-0085)", () => {
    expect(toGridEvent(occurrence, { ...layer("app"), movable: true }).readOnly).toBe(false);
  });

  it("subscribed items never, even if they said yes", () => {
    expect(toGridEvent(occurrence, { ...layer("subscription"), movable: true }).readOnly).toBe(true);
  });

  it("your own items yes", () => {
    expect(toGridEvent(occurrence, layer("own")).readOnly).toBe(false);
  });
});

describe("a background layer", () => {
  const background: Layer = { ...layer("own"), display: "background" };

  it("paints its items as background", () => {
    expect(toGridEvent(occurrence, background).background).toBe(true);
    expect(toGridEvent(occurrence, layer("own")).background).toBe(false);
  });

  it("timed items do not count outside the grid, and whole days do", () => {
    expect(counts(occurrence, background)).toBe(false);
    expect(counts({ ...occurrence, all_day: true, start: "2026-10-06", end: "2026-10-09" }, background)).toBe(true);
    expect(counts(occurrence, layer("own"))).toBe(true);
  });

  it("an older server says nothing and they are events", () => {
    expect(toGridEvent(occurrence, layer("app")).background).toBe(false);
  });
});

describe("the sidebar in groups and the same thing twice", () => {
  const layer = (id: string, name: string, origin: "own" | "subscription" | "app", extra: Record<string, unknown> = {}) =>
    ({ id, name, tone: 1, origin, visible: true, position: 0, connection_id: null, ...extra }) as never;
  const layers = [
    layer("p", "Personal", "own"),
    layer("t", "Work", "own", { days_off_from: ["fc", "fl"] }),
    layer("fl", "Holidays · Local", "own"),
    layer("fc", "Holidays · Region", "subscription", { subscription: { provider: "holidays" } }),
    layer("eq", "Team", "subscription", { subscription: { provider: "football" } }),
    layer("ca", "Races", "subscription", { subscription: { provider: "formula1" } }),
    layer("e1", "Travel · Plan", "app", { app: "travel:plan" }),
    layer("e2", "Travel · Legs", "app", { app: "travel:legs" }),
    layer("e3", "Travel · Trip", "app", { app: "travel:trip" }),
    layer("r", "Training", "app", { app: "training" }),
  ];

  it("four groups, holidays together and apps by app", () => {
    const groups = sidebarGroups(layers);
    expect(groups.own.map((one: { name: string }) => one.name)).toEqual(["Personal", "Work"]);
    expect(groups.holidays.map((one: { name: string }) => one.name)).toEqual(["Holidays · Local", "Holidays · Region"]);
    expect(groups.subscriptions.map((one: { name: string }) => one.name)).toEqual(["Team", "Races"]);
    expect(groups.apps.map((one) => [one.name, one.layers.length])).toEqual([
      ["Travel", 3],
      ["Training", 1],
    ]);
    expect(groups.resting).toEqual(["Work"]);
    expect(shortName(layers[6] as never, "Travel")).toBe("Plan");
  });

  it("yours at the same time with a similar title to an app's is the same", () => {
    const occurrence = (id: string, calendar_id: string, title: string, start = "2027-01-16T09:00:00+01:00") =>
      ({ id, event_id: id, calendar_id, title, all_day: false, start, end: "2027-01-16T13:30:00+01:00", status: "confirmed" }) as never;
    const found = duplicatesOf(
      [
        occurrence("mine", "p", "Museum (collection and gardens)"),
        occurrence("theirs", "e1", "Museum: permanent collection and gardens"),
        occurrence("lunch", "p", "Lunch"),
        occurrence("later", "p", "Museum", "2027-01-16T10:00:00+01:00"),
      ],
      layers,
    );
    expect([...found.keys()]).toEqual(["mine"]);
    expect(similar("Tour of the hills", "Organised tour of the hills")).toBe(true);
    expect(similar("Dinner", "Lunch")).toBe(false);
  });
});
