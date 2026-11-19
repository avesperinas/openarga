import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DemoDoor, doorOf } from "./DemoDoor";

describe("the demo door", () => {
  it("each person is a link that signs in, speaks the chosen language and goes on", () => {
    expect(doorOf("sam", "es", "/money")).toBe("/login/demo?as=sam&locale=es&next=%2Fmoney");
  });

  it("offers both people and both languages, in the language it was opened in", () => {
    const html = renderToStaticMarkup(<DemoDoor initial="en" next="/" />);

    expect(html).toContain("Enter as Alex");
    expect(html).toContain("Enter as Sam");
    expect(html).toContain('href="/login/demo?as=alex&amp;locale=en&amp;next=%2F"');
    expect(html.match(/role="radio"|aria-pressed|segmented/g)?.length ?? 0).toBeGreaterThan(0);
  });
});
