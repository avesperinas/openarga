import { expect, it, vi } from "vitest";

const asked: string[] = [];
vi.mock("../lib/kernel", () => ({
  launchable: (modules: { enabled: boolean }[]) => modules.filter((module) => module.enabled),
  readModules: async () => [
    { id: "notebook", name: "Notebook", enabled: true, search: "/api/notebook/search" },
    { id: "callada", name: "Callada", enabled: true, search: "/api/callada/search" },
    { id: "vieja", name: "Vieja", enabled: false, search: "/api/vieja/search" },
    { id: "vitals", name: "Vitals", enabled: true },
  ],
  readSearch: async (endpoint: string, query: string) => {
    asked.push(`${endpoint}?${query}`);
    return endpoint.includes("notebook") ? { results: [{ title: "Proteína", href: "/notebook/n/1" }] } : null;
  },
}));

const { GET } = await import("./route");

it("reparte lo escrito a las apps habilitadas que buscan, y calla las que no contestan", async () => {
  const response = await GET(new Request("http://shell/search?q=prote%C3%ADna"));

  expect(await response.json()).toEqual({
    groups: [{ app: "notebook", name: "Notebook", results: [{ title: "Proteína", href: "/notebook/n/1" }] }],
  });
  expect(asked).toEqual(["/api/notebook/search?proteína", "/api/callada/search?proteína"]);
});

it("con menos de dos letras no pregunta a nadie", async () => {
  asked.length = 0;
  const response = await GET(new Request("http://shell/search?q=p"));

  expect(await response.json()).toEqual({ groups: [] });
  expect(asked).toEqual([]);
});
