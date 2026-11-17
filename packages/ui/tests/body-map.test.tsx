import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BODY_MUSCLES, BodyMap, BodyMaps, changeColor, muscleOfZone, musclesOn } from "../src/index";

describe("the body", () => {
  it("each Training muscle shows on some side", () => {
    const seen = new Set([...musclesOn("front"), ...musclesOn("back")]);
    expect([...BODY_MUSCLES].filter((muscle) => !seen.has(muscle))).toEqual([]);
  });

  it("the deltoid paints the front head from the front, the rear from the back and otherwise the side", () => {
    expect(muscleOfZone("front", "deltoids", { front_delts: "red" })).toBe("front_delts");
    expect(muscleOfZone("front", "deltoids", { side_delts: "red" })).toBe("side_delts");
    expect(muscleOfZone("back", "deltoids", { rear_delts: "red", side_delts: "blue" })).toBe("rear_delts");
    expect(muscleOfZone("back", "head", {})).toBeNull();
  });

  it("paints each muscle in its colour and the rest empty", () => {
    const html = renderToStaticMarkup(<BodyMap side="back" label="Dorsal" colors={{ lats: "var(--positive)" }} />);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Dorsal"');
    expect(html).toMatch(/data-muscle="lats"><path[^>]*fill="var\(--positive\)"/);
    expect(html).toContain('fill="var(--body-empty)"');
  });

  it("with onSelect, each muscle is a button with its name", () => {
    const html = renderToStaticMarkup(
      <BodyMap side="front" label="Elige" colors={{}} names={{ chest: "Pecho" }} onSelect={() => undefined} />,
    );
    expect(html).toMatch(/role="button" tabindex="0" aria-label="Pecho"/);
  });

  it("the colour of a change: steady between −1 and +1, green up, red down, none without data", () => {
    expect(changeColor(null)).toBeUndefined();
    expect(changeColor(0.8)).toBe("var(--body-steady)");
    expect(changeColor(5)).toContain("var(--positive)");
    expect(changeColor(-5)).toContain("var(--negative)");
    expect(changeColor(30)).toBe(changeColor(10));
  });

  it("compacto, a media altura", () => {
    expect(renderToStaticMarkup(<BodyMaps label="x" colors={{}} compact />)).toContain('data-size="compact"');
  });
});
