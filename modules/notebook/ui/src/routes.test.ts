import { describe, expect, it } from "vitest";

import { pathOf, route } from "./routes";

const ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";

describe("the addresses", () => {
  it("every screen goes and comes back", () => {
    for (const to of [
      { screen: "home" as const },
      { screen: "note" as const, id: ID },
      { screen: "search" as const, q: "präfix", tag: "deutsch" },
      { screen: "trash" as const },
      { screen: "today" as const },
      { screen: "import" as const },
      { screen: "graph" as const },
      { screen: "review" as const },
      { screen: "settings" as const },
    ]) {
      const path = pathOf(to);
      const [pathname, search] = path.split("?");
      expect(route(pathname!, search ? `?${search}` : "")).toEqual(to);
    }
  });

  it("opens on the graph, also for what it does not know; the list of notes has its address", () => {
    expect(route("/notebook")).toEqual({ screen: "graph" });
    expect(route("/notebook/")).toEqual({ screen: "graph" });
    expect(route("/notebook/graph")).toEqual({ screen: "graph" });
    expect(route("/notebook/nothing")).toEqual({ screen: "graph" });
    expect(route("/notebook/notes")).toEqual({ screen: "home" });
    expect(pathOf({ screen: "today" })).toBe("/notebook/today");
  });

  it("the old Spanish addresses still open their screen", () => {
    expect(route(`/notebook/nota/${ID}`)).toEqual({ screen: "note", id: ID });
    expect(route("/notebook/hoy")).toEqual({ screen: "today" });
    expect(route("/notebook/repasar")).toEqual({ screen: "review" });
    expect(route("/notebook/buscar", "?q=x")).toEqual({ screen: "search", q: "x", tag: "" });
  });
});
