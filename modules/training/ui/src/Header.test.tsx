import { renderToString } from "react-dom/server";

import { Backdrop } from "./Backdrop";
import { SettingsScreen } from "./Settings";

describe("el fondo de Training", () => {
  it("se elige en Ajustes, con el de su color como primera opción (ADR-0166)", () => {
    const html = renderToString(
      <Backdrop>
        <SettingsScreen initial={{ settings: { weekly_goal: 5, unit: "kg", default_increments: {} }, gyms: [] }} />
      </Backdrop>,
    );

    expect(html).toContain("Fondo de Training");
    expect(html).toMatch(/aria-pressed="true"[^>]*>.*Su color/);
    expect(html).toContain('data-background="tint"');
    expect(html).not.toContain("data-wallpaper");
    expect(html).toMatch(/src="\/training\/icon.svg\?v=[0-9a-f]{10}"/);
  });
});
