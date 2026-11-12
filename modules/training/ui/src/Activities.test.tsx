import { renderToString } from "react-dom/server";

import { ActivityQuick, ActivitySheet, bandLine, describeActivity, endOf, nowMinute, secondsBetween } from "./Activities";
import type { Activity } from "./api";
import { english, inLocale, spanish } from "./i18n/testing";
import { BandSection } from "./Settings";
import { latestFirst } from "./Today";

const padel: Activity = {
  id: "a1",
  activity_type_id: "t1",
  name: "Padel",
  day: "2026-10-13",
  start_time: "19:04:00",
  duration_seconds: 87 * 60,
  notes: null,
  from_band: true,
  band: { kcal: 612.4, heart_rate_avg: 128.2, heart_rate_max: 171, active_zone_min: 54, distance_km: 3.25 },
};

describe("an activity to the minute", () => {
  it("now goes to the minute, and from one time to another are its seconds", () => {
    expect(nowMinute(new Date(2026, 9, 13, 18, 47))).toBe("18:47");
    expect(secondsBetween("18:47", "19:21")).toBe(34 * 60);
    expect(secondsBetween("23:30", "00:15")).toBe(45 * 60);
    expect(secondsBetween("18:47", "")).toBeNull();
    expect(endOf(padel)).toBe("20:31");
  });

  it("what the band measured is told in one line, in the language of the person", () => {
    expect(bandLine(padel, english, "en")).toBe("612 kcal · average 128 bpm · max 171 · 54 min in zone · 3.3 km");
    expect(bandLine(padel, spanish, "es")).toContain("3,3 km");
    expect(describeActivity(padel, english)).toBe("19:04 · 1 h 27 min · 128 bpm");
  });

  it("a started one says it is ongoing, comes first and is finished from its sheet", () => {
    const open: Activity = { ...padel, id: "a2", day: "2026-10-12", ongoing: true, duration_seconds: null, band: null };
    expect(describeActivity(open, english)).toContain("ongoing");
    expect(latestFirst([padel, open]).map((one) => one.id)).toEqual(["a2", "a1"]);
    const html = renderToString(
      inLocale(<ActivitySheet activity={open} onClose={() => undefined} onRemoved={() => undefined} />),
    );
    expect(html).toContain("Finish");
  });

  it("each activity says what it is called on the band", () => {
    const html = renderToString(
      inLocale(
        <BandSection
          onError={() => undefined}
          initial={[{ id: "t1", name: "Cycling", active: true, band_kinds: ["STATIONARY_BIKE"] }]}
        />,
      ),
    );
    expect(html).toContain("Activities and band");
    expect(html).toContain("Indoor cycling");
    expect(html).toContain('aria-pressed="true"');
  });
});

describe("starting an activity with one tap (T-B05)", () => {
  const types = [
    { id: "t1", name: "Padel", active: true },
    { id: "t2", name: "Climbing", active: true },
    { id: "t3", name: "Rowing", active: false },
  ];

  it("each active activity is a button to start it", () => {
    const html = renderToString(inLocale(<ActivityQuick types={types} ongoing={null} onChanged={() => undefined} />));
    expect(html).toContain('aria-label="Start Padel"');
    expect(html).toContain('aria-label="Start Climbing"');
    expect(html).not.toContain("Start Rowing");
  });

  it("with one ongoing, its time and finishing it", () => {
    const html = renderToString(
      inLocale(
        <ActivityQuick types={types} ongoing={{ ...padel, ongoing: true, duration_seconds: null }} onChanged={() => undefined} />,
      ),
    ).replaceAll("<!-- -->", "");
    expect(html).toContain("Padel");
    expect(html).toContain("Finish");
    expect(html).not.toContain("Start Climbing");
  });
});
