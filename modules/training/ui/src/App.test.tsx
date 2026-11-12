import { renderToString } from "react-dom/server";

import { route } from "./App";
import { TodayScreen } from "./Today";
import type { Today } from "./api";
import { todayLabel } from "./today";
import { inLocale } from "./i18n/testing";

const SETTINGS = { weekly_goal: 5, unit: "kg", default_increments: {} };

const WEEK = { done: 2, goal: 5, monday: "2026-09-14" };

const WITH_PLAN: Today = {
  settings: SETTINGS,
  week: WEEK,
  in_progress: null,
  next: {
    plan_day_id: "d2",
    name: "Pull",
    kind: "pull",
    rotation_number: 3,
    remaining: 2,
    days_in_rotation: 3,
  },
  plan: {
    plan_id: "p",
    name: "Push Pull Leg",
    version_id: "v",
    version: 1,
    valid_from: "2026-09-01",
    days: [
      { id: "d1", name: "Push", kind: "push", position: 1, slots: [] },
      {
        id: "d2",
        name: "Pull",
        kind: "pull",
        position: 2,
        slots: [
          {
            id: "s",
            position: 1,
            exercise: "Row",
            target_sets: 4,
            rep_min: 6,
            rep_max: 10,
            allow_both: false,
            options: [],
          },
        ],
      },
    ],
  },
};

describe("Today", () => {
  it("without a plan it says why it is empty instead of showing a gap", () => {
    const html = renderToString(
      inLocale(
        <TodayScreen
          onOpenSession={() => undefined}
          onOpenPlan={() => undefined}
          now={new Date(2026, 8, 15)}
          initial={{
            status: "ready",
            today: { plan: null, settings: SETTINGS, next: null, in_progress: null, week: WEEK },
          }}
        />,
      ),
    );

    expect(html).toContain("No plan yet");
    expect(html).toContain("Create the plan");
  });

  it("shows the next session and the week against the goal", () => {
    const html = renderToString(inLocale(<TodayScreen onOpenSession={() => undefined} initial={{ status: "ready", today: WITH_PLAN }} />)).replaceAll(
      "<!-- -->",
      "",
    );

    expect(html).toMatch(/Up next ·\s*rotation 3, day 2 of 3/);
    expect(html).toContain("Start Pull");
    expect(html).not.toContain("Start Pull?");
    expect(html).toContain("This week");
    expect(html).toMatch(/class="hint">\d+ of 5 · this month/);
    expect(html).toMatch(/class="goal-week" role="img" aria-label="This week: M, /);
  });

  it("if the API fails it says so, and the rest of the screen stays", () => {
    const html = renderToString(inLocale(<TodayScreen onOpenSession={() => undefined} initial={{ status: "error" }} />));

    expect(html).toContain("Could not load");
    expect(html).toContain("Calendar");
  });

  it("without plan or history the calendar, the week, the month and the latest already show", () => {
    const html = renderToString(
      inLocale(<TodayScreen
        onOpenSession={() => undefined}
        now={new Date(2026, 8, 16)}
        initialSessions={[]}
        initial={{
          status: "ready",
          today: { plan: null, settings: SETTINGS, next: null, in_progress: null, week: WEEK },
        }}
      />),
    ).replaceAll("<!-- -->", "");

    for (const title of ["This week", "Calendar", "Latest workouts", "Activities"]) {
      expect(html).toMatch(new RegExp(`>${title}(<span[^>]*>[^<]*</span>)?</h2>`));
    }
    expect(html).toContain("this month, 0 sessions");
    expect(html).toContain("No workouts yet");
    expect(html).toContain(">Log<");
  });

  it("the date reads like on the arga desktop, in the language of the person", () => {
    expect(todayLabel(new Date(2026, 8, 15), "en")).toBe("Tuesday, September 15");
    expect(todayLabel(new Date(2026, 8, 15), "es")).toBe(
      new Intl.DateTimeFormat("es", { weekday: "long", day: "numeric", month: "long" })
        .format(new Date(2026, 8, 15))
        .replace(/^./, (first) => first.toUpperCase()),
    );
  });
});

describe("Today with a session half done", () => {
  it("offers to continue it instead of starting another", () => {
    const html = renderToString(
      inLocale(<TodayScreen
        onOpenSession={() => undefined}
        initial={{ status: "ready", today: { ...WITH_PLAN, in_progress: "s1" } }}
      />),
    ).replaceAll("<!-- -->", "");

    expect(html).toContain("Continue workout");
    expect(html).not.toContain("Start Pull");
  });
});

describe("routes", () => {
  it("the session has its address, to reload halfway without losing it", () => {
    expect(route("/training/session/5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11")).toEqual({
      screen: "session",
      id: "5b0e8f7e-4c1a-4d53-9a53-0d3f0c1e2a11",
    });
    expect(route("/training/")).toEqual({ screen: "today" });
    expect(route("/training/session/something-else")).toEqual({ screen: "today" });
  });
});

describe("Today recommends and lets you choose", () => {
  it("with the rotation started, another day than the due one can be started (T-B05)", () => {
    const today: Today = {
      ...WITH_PLAN,
      rotation: {
        number: 3,
        open: true,
        days: [
          { plan_day_id: "d1", name: "Push", kind: "push", done: true },
          { plan_day_id: "d2", name: "Pull", kind: "pull", done: false },
        ],
      },
    };
    const html = renderToString(
      inLocale(<TodayScreen onOpenSession={() => undefined} initial={{ status: "ready", today }} />),
    ).replaceAll("<!-- -->", "");

    expect(html).toContain("Start Pull");
    expect(html).toContain(">Another day<");
  });
});

describe("the tabs have an address", () => {
  it("calendar and plan", () => {
    expect(route("/training/calendar")).toEqual({ screen: "history" });
    expect(route("/training/plan/")).toEqual({ screen: "plan" });
    expect(route("/training/next")).toEqual({ screen: "next" });
  });
});
