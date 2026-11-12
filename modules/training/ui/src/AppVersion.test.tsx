import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("where the version shows", () => {
  const screens = ["Today", "History", "Plan"];

  it.each(screens)("%s paints it", (screen) => {
    const source = readFileSync(new URL(`./${screen}.tsx`, import.meta.url), "utf8");

    expect(source).toContain('from "./AppVersion"');
    expect(source).toContain("<AppVersion />");
  });
});
