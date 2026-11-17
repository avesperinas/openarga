import { expect, it, vi } from "vitest";

const asked: string[] = [];
vi.mock("../lib/kernel", () => ({
  launchable: (modules: { enabled: boolean }[]) => modules.filter((module) => module.enabled),
  readModules: async () => [
    { id: "notebook", name: "Notebook", enabled: true, search: "/api/notebook/search" },
    { id: "quiet", name: "Quiet", enabled: true, search: "/api/quiet/search" },
    { id: "vieja", name: "Vieja", enabled: false, search: "/api/vieja/search" },
    { id: "vitals", name: "Vitals", enabled: true },
  ],
  readSearch: async (endpoint: string, query: string) => {
    asked.push(`${endpoint}?${query}`);
    return endpoint.includes("notebook") ? { results: [{ title: "Protein", href: "/notebook/n/1" }] } : null;
  },
}));

const { GET } = await import("./route");

it("hands what was typed to the enabled apps that search, and silences those that do not answer", async () => {
  const response = await GET(new Request("http://shell/search?q=protein"));

  expect(await response.json()).toEqual({
    groups: [{ app: "notebook", name: "Notebook", results: [{ title: "Protein", href: "/notebook/n/1" }] }],
  });
  expect(asked).toEqual(["/api/notebook/search?protein", "/api/quiet/search?protein"]);
});

it("with fewer than two letters it asks nobody", async () => {
  asked.length = 0;
  const response = await GET(new Request("http://shell/search?q=p"));

  expect(await response.json()).toEqual({ groups: [] });
  expect(asked).toEqual([]);
});
