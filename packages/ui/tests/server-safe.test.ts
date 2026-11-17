import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SOURCE = resolve(__dirname, "../src");

describe("what a server component may import from @openarga/ui", () => {
  it("every module that creates a React context is marked as client code", () => {
    const unmarked = readdirSync(SOURCE, { recursive: true, encoding: "utf8" })
      .filter((name) => /\.tsx?$/.test(name))
      .filter((name) => {
        const text = readFileSync(resolve(SOURCE, name), "utf8");
        return /\bcreateContext\s*[<(]/.test(text) && !/^"use client";/.test(text);
      });
    expect(unmarked).toEqual([]);
  });
});
