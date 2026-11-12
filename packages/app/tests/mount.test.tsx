// @vitest-environment jsdom
import { act } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { mountApp } from "../src/mount";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
});

async function asked(id: string, api?: string): Promise<string[]> {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      return new Response(JSON.stringify({ user_id: "00000000-0000-4000-8000-000000000001" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  document.body.innerHTML = '<div id="root"></div>';
  await act(async () => {
    await mountApp(id, <p>app</p>, api ? { api } : {});
    await new Promise((resolve) => setTimeout(resolve, 100));
  });
  return urls;
}

it("por defecto, la API se llama como la app", async () => {
  expect(await asked("library")).toContain("/api/library/me");
});

it("con `api`, la de la app aunque viva en otra dirección", async () => {
  const urls = await asked("kpis", "goals");
  expect(urls).toContain("/api/goals/me");
  expect(urls).not.toContain("/api/kpis/me");
});
