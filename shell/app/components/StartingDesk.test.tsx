import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { StartingDesk } from "./StartingDesk";

describe("the starting desktop in Settings", () => {
  it("says what it brings and offers it for this device, touching nothing until confirmed", () => {
    const html = renderToStaticMarkup(<StartingDesk reload={() => {}} />);

    expect(html).toContain("Desktop");
    expect(html).toContain("Today (agenda, tasks and Claude usage), Health, Money and");
    expect(html).toContain("Use the phone&#x27;s starting one");
    expect(html).not.toContain("Replace");
  });
});
