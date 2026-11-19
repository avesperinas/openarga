// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";

import type { ModuleSummary } from "../lib/kernel";
import { Launcher } from "./Launcher";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const app = (id: string, family: string, badge?: string): ModuleSummary => ({
  id,
  name: id,
  version: "0.1.0",
  enabled: true,
  api_prefix: `/api/${id}`,
  view: `/${id}`,
  family,
  badge,
  scopes: [],
  updated_at: "2026-09-28T00:00:00Z",
});

it("one request to /badges for every companion, and each dot with its own", async () => {
  const asked: string[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    asked.push(String(input));
    return new Response(JSON.stringify({ insights: 3 }), { headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  const container = document.createElement("div");
  const root = createRoot(container);

  await act(async () =>
    root.render(
      <Launcher
        modules={[
          app("insights", "companion", "/api/insights/badge"),
          app("other", "companion", "/api/other/badge"),
          app("vitals", "health"),
        ]}
      />,
    ),
  );
  for (let i = 0; i < 5; i++) await act(async () => await Promise.resolve());

  expect(asked).toEqual(["/badges"]);
  expect(container.querySelector('[aria-label="insights, 3 unseen"] .launcher-dot')).not.toBeNull();
  expect(container.querySelectorAll(".launcher-dot")).toHaveLength(1);
  act(() => root.unmount());
});
