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
    body: "Ir en noviembre, con el hayedo rojo.",
    place: { name: "Selva de Irati", town: "Orbaizeta", country: "España", lat: 42.98, lon: -1.17 },
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

describe("las direcciones", () => {
  it("cada pantalla tiene la suya y vuelve a ella", () => {
    expect(route("/outings/")).toEqual({ tab: "agenda" });
    expect(route("/outings/ganas")).toEqual({ tab: "wishes" });
    expect(route("/outings/ajustes")).toEqual({ tab: "settings" });
    expect(route(`/outings/ganas/${ID}`)).toEqual({ tab: "wish", id: ID });
    expect(route("/outings/ganas/otra-cosa")).toEqual({ tab: "agenda" });
    expect(route(`/outings/eventos/${ID}`)).toEqual({ tab: "event", id: ID });
    expect(route("/outings/explorar")).toEqual({ tab: "explore" });
    expect(route(`/outings/explorar/${ID}`)).toEqual({ tab: "event", id: ID, from: "explore" });
    expect(pathOf({ tab: "event", id: ID, from: "explore" })).toBe(`/outings/explorar/${ID}`);
    expect(pathOf({ tab: "event", id: ID })).toBe(`/outings/eventos/${ID}`);
    expect(pathOf({ tab: "wish", id: ID })).toBe(`/outings/ganas/${ID}`);
  });
});

describe("las ganas", () => {
  it("tres pestañas: excursiones, restaurantes y viajes", () => {
    const all = [
      wish({ id: "a", kind: "eat", name: "Pintxos" }),
      wish({ id: "b", kind: "trip", name: "Japón" }),
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

  it("dice dónde está sin repetir el nombre del sitio", () => {
    expect(placeLine({ name: "Selva de Irati", town: "Orbaizeta", country: "España" })).toBe("Orbaizeta, España");
    expect(placeLine({ name: "Japón", country: "Japón" })).toBe("Japón");
    expect(wishLine(wish({}))).toBe("Selva de Irati · Orbaizeta, España");
    expect(wishLine(wish({ place: null }))).toBe("Ir en noviembre, con el hayedo rojo.");
    expect(cardLine(wish({ name: "Japón", place: { name: "Japón", country: "Japón" }, body: "En primavera." }))).toBe(
      "En primavera.",
    );
    expect(cardLine(wish({}))).toBe("Orbaizeta, España");
  });

  it("la foto lleva su versión y sin foto no hay URL", () => {
    expect(photoUrl(wish({}))).toBeUndefined();
    expect(photoUrl(wish({ has_photo: true, photo_version: "17" }), "thumb")).toBe(
      `/api/outings/wishes/${ID}/photo?size=thumb&v=17`,
    );
  });

  it("la foto de su sitio dice de quién es y con qué licencia", () => {
    const page = "https://commons.wikimedia.org/wiki/File:Sitio.jpg";
    expect(creditLine({ author: "Autora Sintética", license: "CC BY-SA 4.0", page })).toBe(
      "Foto: Autora Sintética · CC BY-SA 4.0 · Wikimedia Commons",
    );
    expect(creditLine({ author: null, license: null, page })).toBe("Foto: autor sin nombre · Wikimedia Commons");
  });

  it("una tarjeta sin foto lleva la placa de su tipo", () => {
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
    title: "Orquesta Sintética",
    starts_on: "2026-10-03",
    ends_on: "2026-10-03",
    time: "19:30",
    venue: "Sala principal",
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

describe("la agenda", () => {
  it("lo que ya está pasando va en Ahora; lo demás, en el día en que empieza", () => {
    const feria = event({ id: "f", title: "Feria", starts_on: "2026-10-01", ends_on: "2026-10-04" });
    const today = event({ id: "t", starts_on: "2026-10-02", ends_on: "2026-10-02" });
    const saturday = event({ id: "s" });
    const { now, days } = arrange([feria, today, saturday], "2026-10-02", "2026-10-02");
    expect(now.map((one) => one.id)).toEqual(["f"]);
    expect(days.map(({ day, events }) => [day, events.map((one) => one.id)])).toEqual([
      ["2026-10-02", ["t"]],
      ["2026-10-03", ["s"]],
    ]);
  });

  it("dice los días como en el lienzo", () => {
    expect(dayTitle("2026-10-03")).toBe("Sábado 3");
    expect(dayTitle("2027-04-10", true)).toBe("Sábado 10 de abril");
    expect(shortDay("2026-10-03")).toBe("Sáb 3");
    expect(span(event({ starts_on: "2026-10-02", ends_on: "2026-10-04" }))).toBe("2 – 4 de octubre");
    expect(span(event({}))).toBe("3 de octubre");
    expect(eventLine(event({ ends_on: "2026-10-04" }))).toBe("Sala principal · Pamplona · hasta el domingo 4");
  });
});

describe("la agenda tuya y explorar", () => {
  it("el calendario marca cada día que dura, con el tono de su categoría", () => {
    const feria = event({ id: "f", category: "festival", starts_on: "2026-10-30", ends_on: "2026-11-01" });
    const marks = marksOf([feria, event({ id: "c" })]);
    expect(Object.keys(marks).sort()).toEqual(["2026-10-03", "2026-10-30", "2026-10-31", "2026-11-01"]);
    expect(marks["2026-10-31"]).toEqual([{ kind: "hue-3", label: "Orquesta Sintética" }]);
    expect(onDay([feria], "2026-10-31").map((one) => one.id)).toEqual(["f"]);
    expect(onDay([feria], "2026-11-02")).toEqual([]);
  });

  it("un mes va de su día uno al último", () => {
    expect(monthSpan(2026, 1)).toEqual(["2026-02-01", "2026-02-28"]);
    expect(monthSpan(2026, 11)).toEqual(["2026-12-01", "2026-12-31"]);
  });

  it("los resultados por mes y día; lo que ya empezó, en el primero", () => {
    const expo = event({ id: "x", starts_on: "2026-09-01", ends_on: "2026-12-01" });
    const later = event({ id: "l", starts_on: "2026-11-05", ends_on: "2026-11-05" });
    const found = byMonth([expo, event({ id: "c" }), later], "2026-10-03");
    expect(found.map(({ month, days }) => [month, days.map(({ day, events }) => [day, events.map((one) => one.id)])])).toEqual([
      ["2026-10-01", [["2026-10-03", ["x", "c"]]]],
      ["2026-11-01", [["2026-11-05", ["l"]]]],
    ]);
  });
});

describe("una gana compartida", () => {
  it("lo dice en su fila", () => {
    expect(wishLine(wish({ space_id: "casa" }))).toBe("Selva de Irati · Orbaizeta, España · Compartida");
    expect(wishLine(wish({ place: null, body: null, space_id: "casa" }))).toBe("Compartida");
  });
});

describe("lo que se planea en otra app", () => {
  it("dice sus fechas, si tiene, y su detalle", () => {
    expect(plannedLine({ starts_on: "2027-11-11", ends_on: "2027-11-14", detail: "4 días" })).toBe(
      "11 nov – 14 nov · 4 días",
    );
    expect(plannedLine({ starts_on: null, ends_on: null, detail: "mar o abr" })).toBe("mar o abr");
  });
});
