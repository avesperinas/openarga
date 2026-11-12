import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("dónde se enseña la versión", () => {
  const screens = ["Today", "History", "Plan"];

  it.each(screens)("%s la pinta", (screen) => {
    const source = readFileSync(new URL(`./${screen}.tsx`, import.meta.url), "utf8");

    expect(source).toContain('from "./AppVersion"');
    expect(source).toContain("<AppVersion />");
  });
});
