import { renderToString } from "react-dom/server";

import { Backdrop } from "./Backdrop";
import { inLocale } from "./i18n/testing";
import { SettingsScreen } from "./Settings";

describe("the Training background", () => {
  it("is chosen in Settings, with its own colour as the first option (ADR-0166)", () => {
    const html = renderToString(
      inLocale(
        <Backdrop>
          <SettingsScreen initial={{ settings: { weekly_goal: 5, unit: "kg", default_increments: {} }, gyms: [] }} />
        </Backdrop>,
      ),
    );

    expect(html).toMatch(/class="background-grid" aria-label="[^"]*Training"/);
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('data-background="tint"');
    expect(html).not.toContain("data-wallpaper");
    expect(html).toMatch(/src="\/training\/icon.svg\?v=[0-9a-f]{10}"/);
  });
});
