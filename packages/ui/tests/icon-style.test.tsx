import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ICON_STYLES, PreviewChoices, styledIcon } from "../src/index";

describe("icon finish", () => {
  it("changes the icon file and keeps its version", () => {
    expect(styledIcon("/vitals/icon.svg?v=abc", "ink")).toBe("/vitals/icon-ink.svg?v=abc");
    expect(styledIcon("/vitals/icon.svg", "paper")).toBe("/vitals/icon-paper.svg");
    expect(styledIcon("/vitals/icon.svg?v=abc", undefined)).toBe("/vitals/icon.svg?v=abc");
    expect(styledIcon("/favicon.svg", "ink")).toBe("/favicon.svg");
  });

  it("there are three, and the first is the usual one", () => {
    expect(ICON_STYLES.map((style) => style.value)).toEqual(["solid", "ink", "paper"]);
  });
});

describe("choosing while seeing how it looks", () => {
  it("is a radio group with the chosen one checked and its preview", () => {
    const html = renderToStaticMarkup(
      <PreviewChoices
        label="Iconos"
        value="ink"
        onChange={() => undefined}
        options={ICON_STYLES.map((style) => ({ ...style, preview: <img alt="" src={`/x-${style.value}.svg`} /> }))}
      />,
    );
    expect(html).toContain('role="radiogroup" aria-label="Iconos"');
    expect(html).toContain('aria-checked="true" tabindex="0" class="preview-choice" data-checked="true"');
    expect(html).toContain('src="/x-paper.svg"');
    expect(html.match(/role="radio"/g)).toHaveLength(3);
  });
});
