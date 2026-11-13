import { createT, missingKeys } from "@openarga/ui";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { AiSettings, AiSpending } from "./ai";
import { AiAttempts, AiForm, choiceOf, spentLine } from "./AiSettings";
import en from "./i18n/en.json";
import es from "./i18n/es.json";

const CATALOGS = { en, es };

const SETTINGS: AiSettings = {
  provider: "anthropic",
  base_url: null,
  fast_model: null,
  smart_model: "claude-opus-5-5",
  monthly_tokens: 2000000,
  key_hint: "…6789",
  own_key: true,
  instance_key: false,
  mine: { provider: "anthropic", base_url: null, fast_model: null, smart_model: "claude-opus-5-5", monthly_tokens: 2000000 },
  updated_at: "2026-11-13T10:00:00Z",
};

const SPENDING: AiSpending = {
  spent: 1234567,
  monthly_tokens: 2000000,
  attempts: [
    {
      id: "a",
      app: "outings",
      capability: "run",
      role: "smart",
      provider: "anthropic",
      model: "claude-opus-5-5",
      status: "over_budget",
      steps: 4,
      input_tokens: 9000,
      output_tokens: 1000,
      detail: "the month's AI budget ran out mid-run",
      summary: null,
      started_at: "2026-11-13T09:00:00Z",
    },
  ],
};

const form = (locale: "en" | "es", settings = SETTINGS) =>
  renderToStaticMarkup(
    <AiForm t={createT(CATALOGS, locale)} settings={settings} onSave={async () => {}} onKey={async () => {}} onForget={async () => {}} />,
  );

describe("the AI settings", () => {
  it("have every text in both languages", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("show the provider, the default models and only the end of the key", () => {
    const html = form("en");
    expect(html).toContain("Default: claude-haiku-5-5");
    expect(html).toContain('value="claude-opus-5-5"');
    expect(html).toContain("Your key ends in …6789.");
    expect(html).toContain('type="password"');
  });

  it("speak Spanish to a Spanish speaker", () => {
    expect(form("es")).toContain("Presupuesto mensual en tokens");
  });

  it("explain what is lost without a provider and hide the model fields", () => {
    const none = { ...SETTINGS, provider: "none" as const, mine: { ...SETTINGS.mine, provider: null } };
    const html = form("en", none);
    expect(html).toContain("everything works except");
    expect(html).not.toContain("Model for quick reading");
  });

  it("start the form from what the person chose, not from the instance", () => {
    expect(choiceOf({ ...SETTINGS, fast_model: "from-instance" }).fast_model).toBeNull();
  });

  it("say what was spent against the budget and why a call failed", () => {
    const t = createT(CATALOGS, "en");
    expect(spentLine(t, SPENDING)).toMatch(/^This month: 1.234.567 of 2.000.000 tokens$/);
    const html = renderToStaticMarkup(<AiAttempts t={t} spending={SPENDING} />);
    expect(html).toContain("Over budget");
    expect(html).toContain("ran out mid-run");
  });
});
