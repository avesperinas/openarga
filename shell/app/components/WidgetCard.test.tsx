import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CatalogueEntry, Envelope, EnvelopeBody, LayoutItem } from "../lib/kernel";
import { WidgetCard } from "./WidgetCard";

const NEXT: CatalogueEntry = {
  source: "training",
  id: "next",
  title: "Siguiente sesión",
  hue: 1,
  kind: "kpi",
  shape: "number",
  sizes: ["2x2"],
  endpoint: "/api/training/widgets/next",
  refresh: 300,
  link: "/training/siguiente",
};

const item: LayoutItem = {
  instance_id: "una",
  source: "training",
  widget: "next",
  x: 0,
  y: 0,
  size: "2x2",
};

const render = (body: EnvelopeBody) => {
  const envelope: Envelope = { state: "ready", updated_at: "2026-09-18T10:00:00Z", body };
  return renderToStaticMarkup(<WidgetCard item={item} entry={NEXT} envelope={envelope} />);
};

describe("el símbolo de la tarjeta", () => {
  it("sale del tono que manda el módulo, que es el del entreno que toca", () => {
    expect(render({ value: "Pull", icon: "pull", icon_hue: 2 })).toContain(
      'class="icon-badge" data-hue="2"',
    );
  });

  it("sin tono propio, el de la tarjeta", () => {
    expect(render({ value: "Pull", icon: "pull" })).toContain('class="icon-badge" data-hue="1"');
  });
});
