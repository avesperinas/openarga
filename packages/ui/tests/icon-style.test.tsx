import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ICON_STYLES, PreviewChoices, styledIcon } from "../src/index";

describe("el acabado de los iconos", () => {
  it("cambia el fichero del icono y conserva su versión", () => {
    expect(styledIcon("/vitals/icon.svg?v=abc", "ink")).toBe("/vitals/icon-ink.svg?v=abc");
    expect(styledIcon("/vitals/icon.svg", "paper")).toBe("/vitals/icon-paper.svg");
    expect(styledIcon("/vitals/icon.svg?v=abc", undefined)).toBe("/vitals/icon.svg?v=abc");
    expect(styledIcon("/favicon.svg", "ink")).toBe("/favicon.svg");
  });

  it("hay tres, y el primero es el de siempre", () => {
    expect(ICON_STYLES.map((style) => style.value)).toEqual(["solid", "ink", "paper"]);
  });
});

describe("elegir viendo cómo queda", () => {
  it("es un grupo de radios con la elegida marcada y su vista previa", () => {
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
