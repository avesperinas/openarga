import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

import { type ModuleSummary, readArea } from "./kernel";

const module = (id: string, panels?: string[]): ModuleSummary => ({
  id,
  name: id,
  version: "1.0.0",
  enabled: true,
  api_prefix: `/api/${id}`,
  panels,
  scopes: [],
  updated_at: "2026-01-01T00:00:00Z",
});

afterEach(() => vi.unstubAllGlobals());

describe("a home area", () => {
  it("asks only the modules whose manifest brings a panel to it", async () => {
    const asked: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      asked.push(url);
      return new Response(JSON.stringify({ area: "work", title: "Study", tabs: [] }));
    });
    const found = await readArea("work", [module("study", ["work"]), module("money", ["money"]), module("garden")]);
    expect(asked).toEqual(["http://study:8000/panel"]);
    expect(found.map((one) => one.source)).toEqual(["study"]);
  });
});
