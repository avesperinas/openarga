import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CatalogueEntry, Envelope, EnvelopeBody, LayoutItem } from "../lib/kernel";
import { WidgetCard } from "./WidgetCard";

const NEXT: CatalogueEntry = {
  source: "training",
  id: "next",
  title: "Next session",
  hue: 1,
  kind: "kpi",
  shape: "number",
  sizes: ["2x2"],
  endpoint: "/api/training/widgets/next",
  refresh: 300,
  link: "/training/siguiente",
};

const item: LayoutItem = {
  instance_id: "one",
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

describe("the card's symbol", () => {
  it("comes from the tone the module sends, the one of the workout due", () => {
    expect(render({ value: "Pull", icon: "pull", icon_hue: 2 })).toContain(
      'class="icon-badge" data-hue="2"',
    );
  });

  it("without its own tone, the card's", () => {
    expect(render({ value: "Pull", icon: "pull" })).toContain('class="icon-badge" data-hue="1"');
  });
});
