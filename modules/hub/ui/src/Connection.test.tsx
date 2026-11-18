import { configureRegional } from "@openarga/ui";
import { renderToString } from "react-dom/server";
import { beforeAll } from "vitest";

import { route } from "./App";

beforeAll(() => configureRegional({ locale: "en-GB" }));
import { budgetLine, calendarLine, landsIn, priceProblem, removeConsequence, RenameSheet, runLine } from "./Connection";
import { AddSheet, missing } from "./Add";
import type { ConnectionDetail, Provider, Run } from "./api";
import { matching, oneAtATime } from "./BankSheet";

const run = (overrides: Partial<Run>): Run => ({
  operation: "holdings",
  started_at: "2026-09-22T05:00:00Z",
  finished_at: "2026-09-22T05:00:02Z",
  outcome: "ok",
  emitted: 0,
  detail: null,
  ...overrides,
});

test("each pass says how it went, and a failure in the source's words", () => {
  expect(runLine(run({ emitted: 3 }))).toBe("Fine, 3 new items");
  expect(runLine(run({ emitted: 1 }))).toBe("Fine, 1 new item");
  expect(runLine(run({}))).toBe("Fine, nothing new");
  expect(runLine(run({ outcome: "error", detail: "Example Exchange 403 305: No active API key." }))).toBe(
    "Failed: Example Exchange 403 305: No active API key.",
  );
  expect(runLine(run({ outcome: "rate_limited" }))).toBe("The source asked to wait");
  expect(runLine(run({ outcome: "running", finished_at: null }))).toBe("Running");
  expect(runLine(run({ operation: "search" }))).toBe("Answered");
  expect(runLine(run({ operation: "run", detail: "Done in 4 turns with claude-opus-5-5. Ready" }))).toBe(
    "Done in 4 turns with claude-opus-5-5. Ready",
  );
});

test("removing a connection says what it brought stays", () => {
  const connection = { provider_name: "Example Exchange" } as ConnectionDetail;

  expect(removeConsequence(connection)).toContain("What it already brought stays in your apps.");
});

test("renaming starts from the current name", () => {
  const html = renderToString(
    <RenameSheet
      connection={{ id: "x", provider: "ical_private", provider_name: "Private calendar", label: "Work" } as ConnectionDetail}
      onClose={() => undefined}
      onSaved={() => undefined}
    />,
  );

  expect(html).toContain("Rename");
  expect(html).toContain('value="Work"');
});

test("a connection has its address, to reload or come from another app", () => {
  const id = "0b7c2f1e-1b1a-4c55-9d1e-8a6f4a3c2b10";

  expect(route(`/hub/${id}`)).toEqual({ screen: "connection", id });
  expect(route("/hub/")).toEqual({ screen: "status" });
  expect(route("/hub/something-else")).toEqual({ screen: "status" });
});

test("status and catalogue are two tabs, each with its address", () => {
  expect(route("/hub")).toEqual({ screen: "status" });
  expect(route("/hub/setup")).toEqual({ screen: "setup" });
  expect(route("/hub/setup/")).toEqual({ screen: "setup" });
});

test("it does not connect until it has all it asks for", () => {
  const exchange = {
    secrets: [
      { key: "api_key", label: "API key", help: "", multiline: false },
      { key: "api_secret", label: "Secret", help: "", multiline: false },
    ],
  } as Provider;

  expect(missing(exchange, { api_key: "abc" })).toEqual(["Secret"]);
  expect(missing(exchange, { api_key: "abc", api_secret: "  " })).toEqual(["Secret"]);
  expect(missing(exchange, { api_key: "abc", api_secret: "def" })).toEqual([]);
});

test("the add sheet says where to get each thing and hides what is pasted", () => {
  const html = renderToString(
    <AddSheet
      provider={{
        id: "exchange",
        name: "Example Exchange",
        description: "Your crypto.",
        capabilities: ["sync"],
        available: true,
        single: true,
        lives_in: null,
        secrets: [{ key: "api_key", label: "API key", help: "In Example Exchange, Settings → API.", multiline: false }],
      }}
      onClose={() => undefined}
      onCreated={() => undefined}
    />,
  );

  expect(html).toContain("Connect Example Exchange");
  expect(html).toContain("In Example Exchange, Settings → API.");
  expect(html).toContain('type="password"');
});

test("the day's accesses are told, and so is running out", () => {

  expect(budgetLine({ limit: 4, used: 1, remaining: 3 })).toBe("3 of 4 accesses left today.");
  expect(budgetLine({ limit: 4, used: 4, remaining: 0 })).toContain("No accesses left today");
});

test("the bank list is searched without accents or case, and a double tap opens one", () => {
  let calls = 0;
  const once = oneAtATime(() => {
    calls += 1;
    return new Promise<string>(() => undefined);
  });

  expect(matching(["Invented Bank", "Caja Rural", "Ibercaja"], "CAJA")).toEqual(["Caja Rural", "Ibercaja"]);
  expect(matching(["Banco A\u00f1il"], "anil")).toEqual(["Banco A\u00f1il"]);
  expect(once()).not.toBeNull();
  expect(once()).toBeNull();
  expect(calls).toBe(1);
});

test("a calendar subscription says what it brings with its settings", () => {

  expect(calendarLine({ provider: "holidays", settings: { country: "ES", region: "ES-NC" } })).toBe(
    "The national public holidays of ES and those of ES-NC.",
  );
  expect(calendarLine({ provider: "formula1", settings: { sessions: ["race", "qualifying", "sprint"] } })).toBe(
    "Each Grand Prix with the race, qualifying and the sprint.",
  );
  expect(calendarLine({ provider: "ical", settings: { url: "https://example.org/team.ics" } })).toBe(
    "The calendar from example.org, every day.",
  );
  expect(calendarLine({ provider: "football", settings: { team: "11", team_name: "Test Team" } })).toBe(
    "The games of Test Team, every six hours.",
  );
  expect(calendarLine({ provider: "prices", settings: {} })).toBeNull();
});

test("a connection says which apps it reaches through the inlets they declare", () => {

  expect(landsIn({ inlets: [] })).toBeNull();
  expect(landsIn({ inlets: [{ key: "planner.calendar", app: "Planner", title: "Calendar", settings: [] }] })).toBe("It lands in Planner.");
  expect(
    landsIn({
      inlets: [
        { key: "money.accounts", app: "Money", title: "Accounts", settings: [] },
        { key: "carrera.movements", app: "Career", title: "Movements", settings: [] },
      ],
    }),
  ).toBe("It lands in Money and Career.");
});

test("a typed price asks for what identifies it and a price above zero", () => {
  expect(priceProblem("  ", "10")).toBe("Type its ISIN or its ticker.");
  expect(priceProblem("VWCE.DE", "0")).toBe("Type a price above zero.");
  expect(priceProblem("VWCE.DE", "abc")).toBe("Type a price above zero.");
  expect(priceProblem("VWCE.DE", "101,25")).toBeNull();
});
