import { configureRegional } from "@openarga/ui";
import { renderToString } from "react-dom/server";
import { beforeAll } from "vitest";

import { ByApp, ProviderSection, Yours, appPath, providerAction, whereItLives } from "./Home";
import type { Connection, Provider } from "./api";

beforeAll(() => configureRegional({ locale: "en-GB" }));

const provider = (overrides: Partial<Provider>): Provider => ({
  id: "exchange",
  name: "Example Exchange",
  description: "",
  capabilities: ["sync"],
  available: false,
  single: false,
  lives_in: null,
  secrets: [],
  ...overrides,
});

const connection = (overrides: Partial<Connection>): Connection => ({
  id: "c1",
  provider: "exchange",
  label: "Example Exchange",
  category: "finance",
  state: "active",
  brief: "Up to date",
  tone: "positive",
  reason: null,
  last_ok_at: null,
  emitted_week: 0,
  ...overrides,
});

test("what is still set up in its app says so and leads there", () => {
  const exchange = provider({ lives_in: "Money" });

  expect(whereItLives(exchange)).toBe("In Money");
  expect(appPath(exchange)).toBe("/money");
});

test("an app name leads to its route", () => {
  expect(appPath(provider({ lives_in: "Recipes" }))).toBe("/recipes");
});

test("what exists nowhere yet does not pretend to", () => {
  const later = provider({ id: "later", name: "Soon" });

  expect(whereItLives(later)).toBe("Coming soon");
  expect(appPath(later)).toBeNull();
});

test("with nothing connected it explains what this is instead of an empty list", () => {
  const html = renderToString(<Yours connections={[]} />);

  expect(html).toContain("Nothing connected here yet");
  expect(html).toContain("your calendars");
});

test("a connection that needs something says what, with its name", () => {
  const html = renderToString(
    <Yours
      connections={[
        {
          id: "1",
          provider: "enable_banking",
          label: "BBVA",
          category: "finance",
          state: "expiring",
          brief: "About to expire",
          tone: "warning",
          reason: "Access to BBVA expires in 3 days.",
          last_ok_at: null,
          emitted_week: 0,
        },
      ]}
    />,
  );

  expect(html).toContain("About to expire");
  expect(html).toContain('data-tone="warning"');
  expect(html).toContain("Access to BBVA expires in 3 days.");
});

test("each section shows its providers and where they are", () => {
  const html = renderToString(
    <ProviderSection
      title="Other sources"
      providers={[provider({ lives_in: "Money" }), provider({ id: "later", name: "Soon" })]}
    />,
  );

  expect(html).toContain("Other sources");
  expect(html).toContain("In Money");
  expect(html).toContain("Coming soon");
});

test("what is already in the hub is added here", () => {
  const exchange = provider({ available: true, single: true });

  expect(whereItLives(exchange)).toBe("Add");
  expect(providerAction(exchange, [])).toEqual({ kind: "add" });
});

test("a single connection already connected opens its page instead of adding another", () => {
  const exchange = provider({ available: true, single: true });

  expect(whereItLives(exchange, true)).toBe("Connected");
  expect(providerAction(exchange, [connection({ id: "c9" })])).toEqual({ kind: "open", id: "c9" });
});

test("what still lives in its app leads there, and what does not exist does nothing", () => {
  expect(providerAction(provider({ lives_in: "Money" }), [])).toEqual({ kind: "app", path: "/money" });
  expect(providerAction(provider({ id: "later" }), [])).toBeNull();
});

test("what another app creates shows here but is added there: a Claude account, from Chuping", () => {
  const claude = provider({ id: "claude", available: true, created_in: "Chuping" });

  expect(whereItLives(claude)).toBe("From Chuping");
  expect(providerAction(claude, [])).toEqual({ kind: "app", path: "/chuping" });
});

test("setup shows the accounts you have, and below them the row to add another", () => {
  const html = renderToString(
    <ProviderSection
      title="Chuping"
      providers={[provider({ id: "claude", name: "Claude", available: true })]}
      connections={[
        connection({ id: "c1", provider: "claude", label: "Personal" }),
        connection({ id: "c2", provider: "claude", label: "Work", brief: "Caducada", tone: "negative" }),
        connection({ id: "c3", provider: "exchange", label: "Example Exchange" }),
      ]}
    />,
  );

  expect(html).toContain("Personal");
  expect(html).toContain("Work");
  expect(html).toContain('data-tone="negative"');
  expect(html).not.toContain("Example Exchange");
  expect(html.indexOf("Work")).toBeLessThan(html.indexOf(">Add<"));
});

test("a single connection already connected is only its connection, with no add row", () => {
  const html = renderToString(
    <ProviderSection
      title="Money"
      providers={[provider({ available: true, single: true })]}
      connections={[connection({ label: "My Example Exchange" })]}
    />,
  );

  expect(html).toContain("My Example Exchange");
  expect(html).toContain("Up to date");
  expect(html).not.toContain(">Add<");
});

describe("by app (ADR-0103)", () => {
  const catalogue = [
    {
      id: "finance",
      name: "Finance",
      providers: [
        provider({ id: "enable_banking", name: "Banks (PSD2)", available: true }),
        provider({ id: "prices", name: "Quotes", available: true }),
      ],
    },
    { id: "books", name: "Books", providers: [provider({ id: "openlibrary", name: "Open Library", available: true })] },
    { id: "weather", name: "Weather", providers: [provider({ id: "open_meteo", name: "Open-Meteo", available: true })] },
  ];
  const apps = {
    apps: [
      {
        module: "money",
        name: "Money",
        view: "/money",
        inlets: [{ key: "money.accounts", title: "Accounts", providers: ["enable_banking", "prices"] }],
        services: [],
      },
      {
        module: "library",
        name: "Library",
        view: "/library",
        inlets: [],
        services: [{ provider: "openlibrary", capabilities: ["books.search"] }],
      },
    ],
    others: ["open_meteo"],
  };

  it("each app with what reaches it, its connections on top, and apart what reaches none", () => {
    const html = renderToString(
      <ByApp apps={apps} catalogue={catalogue} connections={[connection({ id: "b1", provider: "enable_banking", label: "Test Bank" })]} />,
    );

    expect(html).toContain("Money");
    expect(html).toContain("Test Bank");
    expect(html).toContain("Quotes");
    expect(html).toContain("Library");
    expect(html).toContain("Open Library");
    expect(html.indexOf("Library")).toBeLessThan(html.indexOf("Other sources"));
    expect(html).toContain("Open-Meteo");
    expect(html.indexOf("Money")).toBeLessThan(html.indexOf("Test Bank"));
  });
});
