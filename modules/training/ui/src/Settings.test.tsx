import { renderToString } from "react-dom/server";

import { route } from "./App";
import { inLocale, spanish } from "./i18n/testing";
import { SettingsScreen } from "./Settings";

const LOADED = {
  settings: { weekly_goal: 5, unit: "kg", default_increments: {} },
  gyms: [{ id: "g", name: "Test gym", active: true }],
};

describe("the Training settings", () => {
  it("have their tab and their address", () => {
    expect(route("/training/settings")).toEqual({ screen: "settings" });
  });

  it("carry the goal, the weight and the gyms, and below what every app has", () => {
    const html = renderToString(inLocale(<SettingsScreen initial={LOADED} />)).replaceAll("<!-- -->", "");

    expect(html).toContain("Weekly goal");
    expect(html).toContain('class="body-weight');
    expect(html).toContain("The same weight in Health and Nutrition.");
    expect(html).toContain("Test gym");
    expect(html).toContain(">Training<");
  });

  it("speak the language of the person", () => {
    const html = renderToString(inLocale(<SettingsScreen initial={LOADED} />, "es")).replaceAll("<!-- -->", "");

    expect(html).toContain(spanish("settings.weekly_goal"));
    expect(html).toContain(spanish("settings.add_gym"));
  });
});
