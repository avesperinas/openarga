import { afterEach, describe, expect, it } from "vitest";

import { setLocale } from "./lang";
import { LISTS } from "./taste-words";

describe("the shelf names", () => {
  afterEach(() => setLocale("en"));

  it("follow the interface language", () => {
    expect(LISTS.map((one) => one.label)).toEqual(["Read", "Watch", "Listen"]);
    setLocale("es");
    expect(LISTS.map((one) => one.label)).toEqual(["Leer", "Ver", "Escuchar"]);
  });
});
