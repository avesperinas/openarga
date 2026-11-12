import { expect, it, vi } from "vitest";

const asked: string[] = [];
vi.mock("../lib/kernel", () => ({
  launchable: (modules: { enabled: boolean }[]) => modules.filter((module) => module.enabled),
  readModules: async () => [
    { id: "insights", enabled: true, badge: "/api/insights/badge" },
    { id: "callada", enabled: true, badge: "/api/callada/badge" },
    { id: "vieja", enabled: false, badge: "/api/vieja/badge" },
    { id: "vitals", enabled: true },
  ],
  readBadge: async (badge: string) => {
    asked.push(badge);
    return badge.includes("insights") ? 3 : null;
  },
}));

const { GET } = await import("./route");

it("pide los puntos de los módulos habilitados que los declaran, y calla los que no contestan", async () => {
  expect(await (await GET()).json()).toEqual({ insights: 3 });
  expect(asked).toEqual(["/api/insights/badge", "/api/callada/badge"]);
});
