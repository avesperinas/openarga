import { renderToString } from "react-dom/server";

import { pathOf, route } from "./App";
import type { AgendaEvent, Wish } from "./api";
import { creditLine, photoUrl } from "./api";
import { WishCard } from "./Wishes";
import { monthSpan } from "./Agenda";
import { byMonth } from "./Explore";
import {
  arrange,
  cardLine,
  dayTitle,
  eventLine,
  groups,
  marksOf,
  onDay,
  placeLine,
  plannedLine,
  shortDay,
  span,
  wishLine,
} from "./words";

const ID = "00000000-0000-4000-8000-000000000001";

function wish(overrides: Partial<Wish>): Wish {
  return {
    id: ID,
    kind: "getaway",
    name: "Selva de Irati",
    body: "Go in November, with the beech wood red.",
    place: { name: "Selva de Irati", town: "Orbaizeta", country: "Spain", lat: 42.98, lon: -1.17 },
    has_photo: false,
    photo_version: null,
    done_at: null,
    source: "app",
    created_at: "2026-10-02T10:00:00Z",
    updated_at: "2026-10-02T10:00:00Z",
    space_id: null,
    mine: true,
    ...overrides,
  };
}

describe("the routes", () => {
  it("each screen has its own and comes back to it", () => {
    expect(route("/outings/")).toEqual({ tab: "agenda" });
    expect(route("/outings/wishes")).toEqual({ tab: "wishes" });
    expect(route("/outings/settings")).toEqual({ tab: "settings" });
    expect(route(`/outings/wishes/${ID}`)).toEqual({ tab: "wish", id: ID });
    expect(route("/outings/wishes/something-else")).toEqual({ tab: "agenda" });
    expect(route(`/outings/events/${ID}`)).toEqual({ tab: "event", id: ID });
    expect(route("/outings/explore")).toEqual({ tab: "explore" });
    expect(route(`/outings/explore/${ID}`)).toEqual({ tab: "event", id: ID, from: "explore" });
    expect(pathOf({ tab: "event", id: ID, from: "explore" })).toBe(`/outings/explore/${ID}`);
    expect(pathOf({ tab: "event", id: ID })).toBe(`/outings/events/${ID}`);
    expect(pathOf({ tab: "wish", id: ID })).toBe(`/outings/wishes/${ID}`);
  });
});

describe("the wishes", () => {
  it("three tabs: outings, restaurants and trips", () => {
    const all = [
      wish({ id: "a", kind: "eat", name: "Pintxos" }),
      wish({ id: "b", kind: "trip", name: "Japan" }),
      wish({ id: "c", kind: "getaway" }),
      wish({ id: "d", kind: "plan", name: "Robledal" }),
    ];
    const shape = (tab: Parameters<typeof groups>[1]) =>
      groups(all, tab).map((one) => [one.id, one.layout, one.wishes.map((w) => w.id)]);
    expect(shape("outings")).toEqual([
      ["getaway", "cards", ["c"]],
      ["plan", "rows", ["d"]],
    ]);
    expect(shape("eat")).toEqual([["eat", "rows", ["a"]]]);
    expect(shape("trips")).toEqual([["trip", "cards", ["b"]]]);
    expect(groups([], "trips")).toEqual([]);
  });

  it("says where it is without repeating the place's name", () => {
    expect(placeLine({ name: "Selva de Irati", town: "Orbaizeta", country: "Spain" })).toBe("Orbaizeta, Spain");
    expect(placeLine({ name: "Japan", country: "Japan" })).toBe("Japan");
    expect(wishLine(wish({}))).toBe("Selva de Irati · Orbaizeta, Spain");
    expect(wishLine(wish({ place: null }))).toBe("Go in November, with the beech wood red.");
    expect(cardLine(wish({ name: "Japan", place: { name: "Japan", country: "Japan" }, body: "In spring." }))).toBe(
      "In spring.",
    );
    expect(cardLine(wish({}))).toBe("Orbaizeta, Spain");
  });

  it("the photo carries its version and without a photo there is no URL", () => {
    expect(photoUrl(wish({}))).toBeUndefined();
    expect(photoUrl(wish({ has_photo: true, photo_version: "17" }), "thumb")).toBe(
      `/api/outings/wishes/${ID}/photo?size=thumb&v=17`,
    );
  });

  it("the photo of its place says whose it is and its licence", () => {
    const page = "https://commons.wikimedia.org/wiki/File:Sitio.jpg";
    expect(creditLine({ author: "Synthetic Author", license: "CC BY-SA 4.0", page })).toBe(
      "Photo: Synthetic Author · CC BY-SA 4.0 · Wikimedia Commons",
    );
    expect(creditLine({ author: null, license: null, page })).toBe("Photo: unnamed author · Wikimedia Commons");
  });

  it("a card without a photo carries its kind's badge", () => {
    const html = renderToString(<WishCard wish={wish({})} onOpen={() => undefined} />);
    expect(html).toContain("icon-badge");
    expect(html).toContain("Selva de Irati");
    const withPhoto = renderToString(
      <WishCard wish={wish({ has_photo: true, photo_version: "1" })} onOpen={() => undefined} />,
    );
    expect(withPhoto).toContain("<img");
  });
});

function event(overrides: Partial<AgendaEvent>): AgendaEvent {
  return {
    id: "e",
    title: "Synthetic Orchestra",
    starts_on: "2026-10-03",
    ends_on: "2026-10-03",
    time: "19:30",
    venue: "Main hall",
    town: "Pamplona",
    category: "stage",
    summary: null,
    links: [],
    in_calendar: false,
    wish_id: null,
    first_seen: "2026-10-01T03:00:00Z",
    last_seen: "2026-10-01T03:00:00Z",
    programme: [],
    highlight: false,
    dismissed: false,
    zone: "near",
    ...overrides,
  };
}

describe("the agenda", () => {
  it("what is already on goes in Now; the rest, on the day it starts", () => {
    const fair = event({ id: "f", title: "Fair", starts_on: "2026-10-01", ends_on: "2026-10-04" });
    const today = event({ id: "t", starts_on: "2026-10-02", ends_on: "2026-10-02" });
    const saturday = event({ id: "s" });
    const { now, days } = arrange([fair, today, saturday], "2026-10-02", "2026-10-02");
    expect(now.map((one) => one.id)).toEqual(["f"]);
    expect(days.map(({ day, events }) => [day, events.map((one) => one.id)])).toEqual([
      ["2026-10-02", ["t"]],
      ["2026-10-03", ["s"]],
    ]);
  });

  it("says the days as on the canvas", () => {
    expect(dayTitle("2026-10-03")).toBe("Saturday 3");
    expect(dayTitle("2027-04-10", true)).toBe("Saturday 10 April");
    expect(shortDay("2026-10-03")).toBe("Sat 3");
    expect(span(event({ starts_on: "2026-10-02", ends_on: "2026-10-04" }))).toBe("2 – 4 October");
    expect(span(event({}))).toBe("3 October");
    expect(eventLine(event({ ends_on: "2026-10-04" }))).toBe("Main hall · Pamplona · until Sunday 4");
  });
});

describe("your agenda and explore", () => {
  it("the calendar marks every day it lasts, with its category's hue", () => {
    const fair = event({ id: "f", category: "festival", starts_on: "2026-10-30", ends_on: "2026-11-01" });
    const marks = marksOf([fair, event({ id: "c" })]);
    expect(Object.keys(marks).sort()).toEqual(["2026-10-03", "2026-10-30", "2026-10-31", "2026-11-01"]);
    expect(marks["2026-10-31"]).toEqual([{ kind: "hue-3", label: "Synthetic Orchestra" }]);
    expect(onDay([fair], "2026-10-31").map((one) => one.id)).toEqual(["f"]);
    expect(onDay([fair], "2026-11-02")).toEqual([]);
  });

  it("a month runs from its first day to its last", () => {
    expect(monthSpan(2026, 1)).toEqual(["2026-02-01", "2026-02-28"]);
    expect(monthSpan(2026, 11)).toEqual(["2026-12-01", "2026-12-31"]);
  });

  it("results by month and day; what already started, on the first", () => {
    const expo = event({ id: "x", starts_on: "2026-09-01", ends_on: "2026-12-01" });
    const later = event({ id: "l", starts_on: "2026-11-05", ends_on: "2026-11-05" });
    const found = byMonth([expo, event({ id: "c" }), later], "2026-10-03");
    expect(found.map(({ month, days }) => [month, days.map(({ day, events }) => [day, events.map((one) => one.id)])])).toEqual([
      ["2026-10-01", [["2026-10-03", ["x", "c"]]]],
      ["2026-11-01", [["2026-11-05", ["l"]]]],
    ]);
  });
});

describe("a shared wish", () => {
  it("says so in its row", () => {
    expect(wishLine(wish({ space_id: "home" }))).toBe("Selva de Irati · Orbaizeta, Spain · Shared");
    expect(wishLine(wish({ place: null, body: null, space_id: "home" }))).toBe("Shared");
  });
});

describe("what is planned in another app", () => {
  it("says its dates, if it has them, and its detail", () => {
    expect(plannedLine({ starts_on: "2027-11-11", ends_on: "2027-11-14", detail: "4 days" })).toBe(
      "11 Nov – 14 Nov · 4 days",
    );
    expect(plannedLine({ starts_on: null, ends_on: null, detail: "Mar or Apr" })).toBe("Mar or Apr");
  });
});
