import { describe, expect, it } from "vitest";

import { answer, problemOf } from "../src/api";

describe("problemOf", () => {
  it("gives the reason of a 409 and the first one of a 422", () => {
    expect(problemOf({ detail: "there is one already" })).toBe("there is one already");
    expect(problemOf({ detail: [{ msg: "Value error, la cantidad no vale" }] })).toBe("la cantidad no vale");
    expect(problemOf(null)).toBeNull();
  });
});

describe("answer", () => {
  it("a 204 has no body and is not a failure", async () => {
    await expect(answer("/tasks/1", new Response(null, { status: 204 }))).resolves.toBeUndefined();
  });
});
