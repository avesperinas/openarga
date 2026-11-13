import { describe, expect, it } from "vitest";

import { route, tabOf } from "./App";
import { parseSteps } from "./Settings";

describe("the Vitals addresses", () => {
  it("each page has its own, and anything else is Today", () => {
    expect(route("/vitals/")).toBe("today");
    expect(route("/vitals")).toBe("today");
    expect(route("/vitals/training")).toBe("training");
    expect(route("/vitals/health")).toBe("health");
    expect(route("/vitals/steps")).toBe("steps");
    expect(route("/vitals/sleep")).toBe("sleep");
    expect(route("/vitals/weight")).toBe("weight");
    expect(route("/vitals/body")).toBe("body");
    expect(route("/vitals/labs")).toBe("labs");
    expect(route("/vitals/settings/")).toBe("settings");
    expect(route("/vitals/other")).toBe("today");
  });

  it("the Health pages keep their tab lit", () => {
    expect(tabOf(route("/vitals/labs"))).toBe("health");
    expect(tabOf(route("/vitals/steps"))).toBe("health");
    expect(tabOf(route("/vitals/training"))).toBe("training");
  });
});

describe("the steps goal", () => {
  it("accepts thousands separators and rejects what are not steps", () => {
    expect(parseSteps("8.000")).toBe(8000);
    expect(parseSteps("8000")).toBe(8000);
    expect(parseSteps("8,000")).toBe(8000);
    expect(parseSteps("")).toBeNull();
    expect(parseSteps("50")).toBeNull();
    expect(parseSteps("plenty")).toBeNull();
  });
});
