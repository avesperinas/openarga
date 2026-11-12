import { beforeEach, describe, expect, it, vi } from "vitest";

const asked: string[] = [];
vi.mock("../lib/kernel", () => ({
  readCatalogue: async () => [{ source: "vitals", id: "steps", endpoint: "/api/vitals/widgets/steps" }],
  readWidget: async (url: string) => {
    asked.push(url);
    return { state: "ready", updated_at: "2026-10-21T08:00:00Z", body: {} };
  },
}));

const { GET } = await import("./route");

const ask = (keys: string[]) =>
  GET(new Request(`http://shell/envelopes?${keys.map((key) => `w=${encodeURIComponent(key)}`).join("&")}`));

describe("los sobres en lote (T-V07)", () => {
  beforeEach(() => {
    asked.length = 0;
  });

  it("una clave repetida se pide una vez", async () => {
    const body = await (await ask(Array.from({ length: 64 }, () => "vitals/steps"))).json();

    expect(asked).toEqual(["/api/vitals/widgets/steps"]);
    expect(Object.keys(body)).toEqual(["vitals/steps"]);
  });

  it("lo que no es del catálogo no se traduce a ninguna dirección", async () => {
    const body = await (await ask(["vitals/nope", "../../admin", "vitals/steps?a b"])).json();

    expect(body).toEqual({ "vitals/nope": null, "../../admin": null, "vitals/steps?a b": expect.any(Object) });
    expect(asked).toEqual(["/api/vitals/widgets/steps?option=a%20b"]);
  });
});
