import { describe, expect, it } from "vitest";

import { type Contributor, groupPanelPages, panelAreaOf, panelEntries, placedAreas, withPanelPages, ask, compose, hidePanel, movePanel, orderOf, plain, showPanel, shownAreas, splitActing, toneOf } from "./panels";

const planner: Contributor = {
  source: "planner",
  name: "Planner",
  panel: {
    area: "day",
    order: 10,
    headlines: [{ text: "Dentist at 17:00", priority: 40 }],
    tabs: [{ id: "today", label: "Agenda", blocks: [{ type: "figure", label: "Now", value: "Free" }] }],
    questions: [{ text: "What do I have today?", words: ["agenda", "today", "appointments"], tab: "today" }],
  },
};

const goals: Contributor = {
  source: "goals",
  name: "KPIs",
  panel: {
    area: "day",
    order: 20,
    headlines: [{ text: "You have 2 overdue tasks", tone: "warning", priority: 60 }],
    tabs: [
      {
        id: "tasks",
        label: "Tasks",
        blocks: [{ type: "tasks", widget: "today", items: [], add: "Add" }],
      },
    ],
    questions: [{ text: "What do I have to do?", words: ["tasks", "pending"], tab: "tasks" }],
  },
};

const study: Contributor = {
  source: "study",
  name: "Study",
  panel: {
    area: "work",
    tabs: [
      {
        id: "holidays",
        label: "Holidays",
        blocks: [
          { type: "rings", items: [] },
          { type: "figure", label: "Holidays", value: "11 of 23 days" },
        ],
      },
    ],
    questions: [{ text: "How many holidays do I have left?", words: ["holidays", "days off"], tab: "holidays", block: 1 }],
  },
};

describe("compose", () => {
  it("joins an area's apps: the most important sentence leads and tabs go in their order", () => {
    const day = compose([goals, planner])[0]!;
    expect(day.key).toBe("day");
    expect(day.apps).toBe("Planner · KPIs");
    expect(day.headline?.text).toBe("You have 2 overdue tasks");
    expect(toneOf(day)).toBe("warning");
    expect(day.tabs.map((tab) => tab.id)).toEqual(["planner.today", "goals.tasks"]);
  });

  it("checkboxes carry their app first, so ticking goes to the right one", () => {
    const block = compose([goals])[0]!.tabs[0]!.blocks[0]!;
    expect(block.type === "tasks" && block.widget).toBe("goals/today");
    expect(splitActing("goals/today")).toEqual({ source: "goals", widget: "today" });
  });

  it("follows the owner's order, hides the removed ones and leaves out the empty ones", () => {
    expect(compose([planner, study], { order: ["work", "day"] }).map((area) => area.key)).toEqual(["work", "day"]);
    expect(compose([planner, study], { hidden: ["day"] }).map((area) => area.key)).toEqual(["work"]);
    expect(compose([]).length).toBe(0);
  });

  it("the saved order is completed with the usual one and forgets what is not an area", () => {
    expect(orderOf(["mind", "nothing", "day"])).toEqual(["mind", "day", "money", "health", "work", "home", "leisure"]);
  });
});

describe("ask", () => {
  const areas = compose([planner, goals, study]);

  it("answers ignoring accents and case, with the block that answers", () => {
    const first = ask(areas, "H\u00d3lidays")[0]!;
    expect(first.area).toBe("work");
    expect(first.tab).toBe("study.holidays");
    expect(first.block).toEqual({ type: "figure", label: "Holidays", value: "11 of 23 days" });
  });

  it("by the start of a word, and with at least two letters", () => {
    expect(ask(areas, "task").map((answer) => answer.tab)).toEqual(["goals.tasks"]);
    expect(ask(areas, "t")).toEqual([]);
    expect(ask(areas, "mortgage")).toEqual([]);
  });

  it("plain removes accents and case", () => {
    expect(plain("  H\u00f3w Many Hol\u00cddays? ")).toBe("how many holidays?");
  });
});

describe("which panels you have placed", () => {
  it("without a choice, the starting ones; with your choice, yours in your order", () => {
    expect(shownAreas()).toEqual(["day", "money", "health"]);
    expect(shownAreas({ order: ["work", "day"], hidden: ["money", "health", "home", "leisure", "mind"] })).toEqual(["work", "day"]);
  });

  it("placing one puts it last; removing it hides it; moving it changes its place among those you see", () => {
    const added = showPanel(undefined, "work");
    expect(shownAreas(added)).toEqual(["day", "money", "health", "work"]);
    expect(shownAreas(hidePanel(added, "money"))).toEqual(["day", "health", "work"]);
    expect(shownAreas(movePanel(added, "work", -1))).toEqual(["day", "money", "work", "health"]);
    expect(shownAreas(movePanel(added, "day", -1))).toEqual(["day", "money", "health", "work"]);
  });
});

describe("panels as widgets", () => {
  it("each area gives two: the whole panel, tall, and a single tab chosen when placed", () => {
    const money = panelEntries().filter((entry) => entry.id.startsWith("money"));
    expect(money.map((entry) => [entry.id, entry.sizes[0], entry.option?.endpoint ?? null])).toEqual([
      ["money", "4x6", null],
      ["money.tab", "2x2", "/panels/choices?area=money"],
    ]);
  });

  it("a widget knows its area, and a desktop, the areas to request", () => {
    expect(panelAreaOf({ source: "panel", widget: "work.tab" })).toBe("work");
    expect(panelAreaOf({ source: "money", widget: "money" })).toBeNull();
    expect(panelAreaOf({ source: "panel", widget: "nothing" })).toBeNull();
    const pages = [
      { items: [{ source: "panel", widget: "day" }, { source: "vitals", widget: "weight" }] },
      { items: [{ source: "panel", widget: "day.tab" }, { source: "panel", widget: "work" }] },
    ];
    expect(placedAreas(pages)).toEqual(["day", "work"]);
  });
});

describe("the move from panel pages to widgets", () => {
  const widgets = { id: "w", items: [{ instance_id: "a", source: "vitals", widget: "weight", size: "2x2" as const }] };
  let n = 0;
  const id = () => `id-${++n}`;

  it("the old panels become pages with their whole panel, first and in their order", () => {
    const desk = withPanelPages({ pages: [widgets] }, ["day", "money"], id);
    expect(desk.pages.map((page) => page.id)).toEqual(["panel-day", "panel-money", "w"]);
    expect(desk.pages[0]!.items[0]).toMatchObject({ source: "panel", widget: "day", size: "4x6" });
  });

  it("if a panel is already placed, it touches nothing", () => {
    const placed = { pages: [{ id: "x", items: [{ instance_id: "p", source: "panel", widget: "work", size: "4x6" as const }] }] };
    expect(withPanelPages(placed, ["day"], id)).toBe(placed);
  });
});

describe("on the computer, several panels together", () => {
  const panel = (area: string, id = area) => ({ instance_id: id, source: "panel", widget: area, size: "4x6" as const });
  const single = (area: string) => ({ id: `panel-${area}`, items: [panel(area)] });
  const widgets = { id: "w", items: [{ instance_id: "a", source: "vitals", widget: "weight", size: "2x2" as const }] };

  it("the move on the computer puts three panels per page", () => {
    let n = 0;
    const desk = withPanelPages({ pages: [widgets] }, ["day", "money", "health", "work"], () => `i${++n}`, 3);
    expect(desk.pages.map((page) => [page.id, page.items.map((item) => item.widget)])).toEqual([
      ["panel-day", ["day", "money", "health"]],
      ["panel-work", ["work"]],
      ["w", ["weight"]],
    ]);
  });

  it("the one-panel pages the move left are joined three at a time, and nothing else", () => {
    const before = { pages: [single("day"), single("money"), single("health"), single("work"), widgets] };
    const after = groupPanelPages(before);
    expect(after.pages.map((page) => [page.id, page.items.map((item) => item.widget)])).toEqual([
      ["panel-day", ["day", "money", "health"]],
      ["panel-work", ["work", "weight"]],
    ]);
    expect(groupPanelPages(after)).toBe(after);
  });

  it("what you touched does not move: a page with widgets or another name breaks the group", () => {
    const touched = { id: "panel-money", items: [panel("money"), { instance_id: "x", source: "money", widget: "cash", size: "2x2" as const }] };
    const mine = { id: "1b2c", items: [panel("work")] };
    const desk = { pages: [single("day"), touched, mine, single("health")] };
    expect(groupPanelPages(desk)).toBe(desk);
  });
});

describe("what does not fit next to the last panel", () => {
  it("if the following widgets do not fit in the gap, they stay on their page", () => {
    const many = { id: "w", items: Array.from({ length: 4 }, (_, i) => ({ instance_id: `k${i}`, source: "vitals", widget: `w${i}`, size: "4x4" as const })) };
    const single = (area: string) => ({ id: `panel-${area}`, items: [{ instance_id: area, source: "panel", widget: area, size: "4x6" as const }] });
    const after = groupPanelPages({ pages: [single("day"), single("money"), many] });
    expect(after.pages.map((page) => page.id)).toEqual(["panel-day", "w"]);
  });
});
