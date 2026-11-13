// @vitest-environment jsdom
import { money } from "@openarga/ui";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

import { forgetPreferences } from "../src/preferences";
import { RegionalRoot } from "../src/regional";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  forgetPreferences();
  localStorage.clear();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

function Price() {
  return <p>{money(1234.5).replace(/\u00a0/g, " ")}</p>;
}

it("formats with the person's preferences as soon as they arrive, and remembers them", async () => {
  const mine = { locale: "en", timezone: "America/Chicago", currency: "USD", country: "US", region: null, area: null };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(mine), { status: 200, headers: { "content-type": "application/json" } })),
  );
  document.body.innerHTML = '<div id="root"></div>';
  const root = createRoot(document.getElementById("root")!);
  await act(async () => {
    root.render(
      <RegionalRoot>
        <Price />
      </RegionalRoot>,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
  });

  expect(document.body.textContent).toBe("$1,234.50");
  expect(JSON.parse(localStorage.getItem("arga-preferences") ?? "null")).toEqual(mine);
  act(() => root.unmount());
});
