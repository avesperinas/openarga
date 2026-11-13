import { describe, expect, it } from "vitest";

import { english, spanish } from "./i18n/testing";
import { daySentence, daysStarted, moveVerdict, pace, recoveryLine, recoveryVerdict, sleepVerdict, trainVerdict, weekDots } from "./today";

describe("the pace of the week, so far", () => {
  it("a Thursday is compared with four sevenths of the average, not the whole week", () => {
    const thursday = new Date("2026-11-05T12:00:00");
    expect(daysStarted(thursday)).toBe(4);
    expect(pace(240, 520, thursday)).toBeCloseTo(240 / ((520 * 4) / 7));
    expect(trainVerdict(pace(240, 520, thursday), english)).toEqual({ code: "slightly_below", verdict: "Slightly below", tone: "neutral" });
  });

  it("Monday counts one day and Sunday seven", () => {
    expect(daysStarted(new Date("2026-11-02T12:00:00"))).toBe(1);
    expect(daysStarted(new Date("2026-11-08T12:00:00"))).toBe(7);
    expect(pace(520, 520, new Date("2026-11-08T12:00:00"))).toBe(1);
  });

  it("without an average, there is no pace", () => {
    expect(pace(100, null, new Date())).toBeNull();
    expect(trainVerdict(null, english).verdict).toBe("No average yet");
  });
});

describe("the words of Today", () => {
  it("sleep by its quality and how you start the day, with 50 the usual", () => {
    expect(sleepVerdict({ value: 81, quality: "good", duration: 40, depth: 20, calm: 21 }, english)?.verdict).toBe("Good");
    expect(recoveryVerdict(74, english)?.verdict).toBe("Better than usual");
    expect(recoveryVerdict(50, english)?.verdict).toBe("As usual");
    expect(recoveryVerdict(30, english)?.tone).toBe("fair");
    expect(recoveryLine(1.2, -0.8, english)).toBe("HRV high, resting low");
  });

  it("the steps with their average, in the language of the person", () => {
    const steps = { today: 3200, mean_7: 8000, mean_7_past: 8100, mean_30: 9000, goal: 8000 };
    expect(moveVerdict(steps, english, "en")).toEqual({
      code: "moving",
      verdict: "3,200 steps",
      tone: "neutral",
      detail: "7-day average: 8,100",
    });
    expect(moveVerdict(steps, spanish, "es").verdict).toBe(spanish("steps.count", { count: "3200" }));
  });

  it("the sentence joins whatever there is", () => {
    expect(
      daySentence(
        {
          sleep: sleepVerdict({ value: 81, quality: "good", duration: 40, depth: 20, calm: 21 }, english),
          recovery: recoveryVerdict(74, english),
          train: trainVerdict(0.7, english),
        },
        english,
      ),
    ).toBe("You slept well and you start better than usual. This week you are slightly below your pace.");
    expect(daySentence({}, english)).toBe("");
  });

  it("the days of the week, with what is done and what is left", () => {
    const days = weekDots([], new Date("2026-11-05T12:00:00"));
    expect(days.map((one) => one.state)).toEqual(["missed", "missed", "missed", "today", "future", "future", "future"]);
  });
});
