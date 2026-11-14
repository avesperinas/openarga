import { describe, expect, it } from "vitest";

import { toneIndex } from "./GraphView";

describe("the colour of a folder", () => {
  it("is always the same, ignoring case, and the root has none", () => {
    expect(toneIndex("Study/German", 10)).toBe(toneIndex("study/german", 10));
    expect(toneIndex("Study/German", 10)).toBeGreaterThanOrEqual(0);
    expect(toneIndex("Study/German", 10)).toBeLessThan(10);
    expect(toneIndex("", 10)).toBe(-1);
  });
});
