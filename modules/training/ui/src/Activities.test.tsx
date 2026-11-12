import { renderToString } from "react-dom/server";

import { ActivityQuick, ActivitySheet, bandLine, describeActivity, endOf, nowMinute, secondsBetween } from "./Activities";
import type { Activity } from "./api";
import { BandSection } from "./Settings";
import { latestFirst } from "./Today";

const padel: Activity = {
  id: "a1",
  activity_type_id: "t1",
  name: "Pádel",
  day: "2026-10-13",
  start_time: "19:04:00",
  duration_seconds: 87 * 60,
  notes: null,
  from_band: true,
  band: { kcal: 612.4, heart_rate_avg: 128.2, heart_rate_max: 171, active_zone_min: 54 },
};

describe("una actividad al minuto", () => {
  it("la hora de ahora va al minuto, y de una hora a otra son sus segundos", () => {
    expect(nowMinute(new Date(2026, 9, 13, 18, 47))).toBe("18:47");
    expect(secondsBetween("18:47", "19:21")).toBe(34 * 60);
    expect(secondsBetween("23:30", "00:15")).toBe(45 * 60);
    expect(secondsBetween("18:47", "")).toBeNull();
    expect(endOf(padel)).toBe("20:31");
  });

  it("lo que midió la pulsera se dice en una línea", () => {
    expect(bandLine(padel)).toBe("612 kcal · media 128 lpm · máx. 171 · 54 min en zona");
    expect(describeActivity(padel)).toBe("19:04 · 1 h 27 min · 128 lpm");
  });

  it("una empezada dice que está en curso, sale la primera y se termina desde su hoja", () => {
    const open: Activity = { ...padel, id: "a2", day: "2026-10-12", ongoing: true, duration_seconds: null, band: null };
    expect(describeActivity(open)).toContain("en curso");
    expect(latestFirst([padel, open]).map((one) => one.id)).toEqual(["a2", "a1"]);
    const html = renderToString(<ActivitySheet activity={open} onClose={() => undefined} onRemoved={() => undefined} />);
    expect(html).toContain("Terminar");
  });

  it("cada actividad dice cómo se llama en la pulsera", () => {
    const html = renderToString(
      <BandSection
        onError={() => undefined}
        initial={[{ id: "t1", name: "Bici", active: true, band_kinds: ["STATIONARY_BIKE"] }]}
      />,
    );
    expect(html).toContain("Actividades y pulsera");
    expect(html).toContain("Bici estática");
    expect(html).toContain('aria-pressed="true"');
  });
});

describe("empezar una actividad de un toque (T-B05)", () => {
  const types = [
    { id: "t1", name: "Pádel", active: true },
    { id: "t2", name: "Escalada", active: true },
    { id: "t3", name: "Remo", active: false },
  ];

  it("cada actividad activa es un botón para empezarla", () => {
    const html = renderToString(<ActivityQuick types={types} ongoing={null} onChanged={() => undefined} />);
    expect(html).toContain('aria-label="Empezar Pádel"');
    expect(html).toContain('aria-label="Empezar Escalada"');
    expect(html).not.toContain("Empezar Remo");
  });

  it("con una en curso, su tiempo y terminarla", () => {
    const html = renderToString(
      <ActivityQuick types={types} ongoing={{ ...padel, ongoing: true, duration_seconds: null }} onChanged={() => undefined} />,
    ).replaceAll("<!-- -->", "");
    expect(html).toContain("Pádel");
    expect(html).toContain("Terminar");
    expect(html).not.toContain("Empezar Escalada");
  });
});
