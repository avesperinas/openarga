import { describe, expect, it } from "vitest";

import { answer, problemOf } from "../src/api";

describe("problemOf", () => {
  it("da el motivo de un 409 y el primero de un 422", () => {
    expect(problemOf({ detail: "ya hay uno" })).toBe("ya hay uno");
    expect(problemOf({ detail: [{ msg: "Value error, la cantidad no vale" }] })).toBe("la cantidad no vale");
    expect(problemOf(null)).toBeNull();
  });
});

describe("answer", () => {
  it("un 204 no tiene cuerpo y no es un fallo", async () => {
    await expect(answer("/tasks/1", new Response(null, { status: 204 }))).resolves.toBeUndefined();
  });
});
