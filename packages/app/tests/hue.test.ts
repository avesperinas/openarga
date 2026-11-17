import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { manifestHue, manifestTone } from "../src/vite";

function app(manifest: string): string {
  const root = mkdtempSync(join(tmpdir(), "arga-hue-"));
  mkdirSync(join(root, "ui"));
  writeFileSync(join(root, "manifest.yaml"), manifest);
  return join(root, "ui");
}

const page = '<!doctype html>\n<html lang="en">\n<body></body></html>';

describe("an app's tone", () => {
  it("comes from ui.hue in its manifest, not from a widget's", () => {
    const dir = app("id: garden\nui:\n  view: /garden\n  hue: 7\n  widgets:\n    - id: a\n      hue: 2\n");
    expect(manifestHue(dir)).toBe(7);
    const tone = manifestTone(dir).transformIndexHtml as (html: string) => string;
    expect(tone(page)).toContain('<html data-hue="7" lang="en">');
  });

  it("leaves the page alone when the manifest has none", () => {
    const dir = app("id: garden\nui:\n  view: /garden\n");
    expect(manifestHue(dir)).toBeNull();
    const tone = manifestTone(dir).transformIndexHtml as (html: string) => string;
    expect(tone(page)).toBe(page);
  });
});
