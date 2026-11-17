"use client";

import {
  CopyField,
  Hint,
  IconButton,
  type Locale,
  Switch,
  ICON_STYLES,
  PreviewChoices,
  Section,
  SegmentedControl,
  type SegmentedOption,
  SelectField,
  Slider,
  TextField,
  VersionTag,
  styledIcon,
} from "@openarga/ui";
import * as React from "react";

import { appIconOf } from "../lib/app-icons";
import type { ModuleSummary } from "../lib/kernel";
import { APP_NAME_MAX, APP_NAME_SETS, type AppNameSet, OPACITY_RANGE, type UiPreferences, appNameOf } from "../lib/preferences";
import { AREAS, hiddenOf, orderOf } from "../lib/panels";
import { Notifications } from "./Notifications";
import { RegionSettings } from "./RegionSettings";
import { Spaces } from "./Spaces";
import { StartingDesk } from "./StartingDesk";
import { usePlatformVersion } from "./Version";
import { WallpaperSheet } from "./Desktop";
import { say } from "../words";

const themes = (): SegmentedOption<UiPreferences["theme"]>[] => [
  { value: "system", label: say("settings.theme.system"), icon: "system" },
  { value: "light", label: say("settings.theme.light"), icon: "sun" },
  { value: "dark", label: say("settings.theme.dark"), icon: "moon" },
];

export const CLAUDE_CLIENT_ID = "claude";

export function Settings({
  preferences,
  onChange,
  modules = [],
  locale = "en",
}: {
  preferences: UiPreferences;
  onChange: (next: Partial<UiPreferences>) => void;
  modules?: ModuleSummary[];
  locale?: Locale;
}) {
  return (
    <div className="settings">
      <RegionSettings locale={locale} />

      <Section title={say("settings.glass.title")}>
        <div className="settings-row">
          <Slider
            label={say("settings.glass")}
            min={OPACITY_RANGE.min}
            max={OPACITY_RANGE.max}
            step={OPACITY_RANGE.step}
            value={preferences.glass_opacity}
            valueText={say("settings.glass.percent", { n: Math.round(preferences.glass_opacity * 100) })}
            onChange={(glass_opacity) => onChange({ glass_opacity })}
          />
          <output className="settings-value">
            {Math.round(preferences.glass_opacity * 100)}%
          </output>
        </div>
        <Hint>
          {preferences.glass_opacity >= 1
            ? say("settings.glass.opaque")
            : say("settings.glass.hint")}
        </Hint>
      </Section>

      <Section title={say("settings.theme")}>
        <SegmentedControl
          label={say("settings.theme")}
          options={themes()}
          value={preferences.theme}
          onChange={(theme) => onChange({ theme })}
        />
      </Section>

      <IconStyles preferences={preferences} onChange={onChange} modules={modules} />

      <WallpaperSheet />

      <StartingDesk />

      <AppNames preferences={preferences} onChange={onChange} modules={modules} />

      <Spaces />

      <Notifications />

      <ConnectClaude />

      <Versions modules={modules} />
    </div>
  );
}

const PREVIEWED = ["planner", "training", "library", "money", "shopping"];

export function IconStyles({
  preferences,
  onChange,
  modules,
}: {
  preferences: Pick<UiPreferences, "icon_style">;
  onChange: (next: Partial<UiPreferences>) => void;
  modules: ModuleSummary[];
}) {
  const shown = PREVIEWED.map((id) => modules.find((module) => module.id === id && module.view))
    .filter((module): module is ModuleSummary => Boolean(module))
    .slice(0, 3);
  return (
    <Section title={say("settings.icons")}>
      <PreviewChoices
        label={say("settings.icons.finish")}
        value={preferences.icon_style ?? "solid"}
        onChange={(icon_style) => onChange({ icon_style })}
        options={ICON_STYLES.map((style) => ({
          ...style,
          preview: shown.map((module) => <img key={module.id} src={styledIcon(appIconOf(module)!, style.value)} alt="" />),
        }))}
      />
      <Hint>{say("settings.icons.hint")}</Hint>
    </Section>
  );
}

export function AppNames({
  preferences,
  onChange,
  modules,
}: {
  preferences: Pick<UiPreferences, "app_names" | "custom_app_names">;
  onChange: (next: Partial<UiPreferences>) => void;
  modules: ModuleSummary[];
}) {
  const set = preferences.app_names ?? "standard";
  const custom = preferences.custom_app_names ?? {};

  const choose = (next: AppNameSet) => {
    if (next !== "custom" || Object.keys(custom).length > 0) return onChange({ app_names: next });
    const seeded = Object.fromEntries(
      modules.map((module) => [module.id, appNameOf(module.id, module.name, preferences)]),
    );
    onChange({ app_names: next, custom_app_names: seeded });
  };

  const rename = (id: string, value: string) => {
    const others = Object.fromEntries(Object.entries(custom).filter(([key]) => key !== id));
    const name = value.slice(0, APP_NAME_MAX);
    onChange({ custom_app_names: name.trim() ? { ...others, [id]: name } : others });
  };

  return (
    <Section title={say("settings.names")}>
      <SelectField label={say("settings.names")} hideLabel options={APP_NAME_SETS} value={set} onChange={choose} />
      {set === "custom" ? (
        <div className="settings-fields">
          {modules.map((module) => (
            <TextField
              key={module.id}
              label={module.name}
              value={custom[module.id] ?? ""}
              placeholder={module.name}
              onChange={(value) => rename(module.id, value)}
            />
          ))}
        </div>
      ) : (
        <Hint>{modules.map((module) => appNameOf(module.id, module.name, preferences)).join(" · ")}</Hint>
      )}
      <Hint>{say("settings.names.hint")}</Hint>
    </Section>
  );
}

export function Versions({ modules, platform }: { modules: ModuleSummary[]; platform?: string }) {
  const version = usePlatformVersion(platform);

  return (
    <Section title={say("settings.versions")}>
      <ul className="version-list">
        <li>
          <VersionTag name="arga" version={version || "…"} />
        </li>
        {modules.map((module) => (
          <li key={module.id}>
            <VersionTag name={module.id} version={module.version} />
          </li>
        ))}
      </ul>
      <Hint>{say("settings.versions.hint")}</Hint>
    </Section>
  );
}

export function ConnectClaude({ origin }: { origin?: string }) {
  const [here, setHere] = React.useState(origin ?? "");
  React.useEffect(() => {
    if (!origin) setHere(window.location.origin);
  }, [origin]);
  return (
    <Section title={say("settings.claude")}>
      <Hint>{say("settings.claude.hint")}</Hint>
      <ol className="settings-steps">
        <li>{say("settings.claude.step1")}</li>
        <li>{say("settings.claude.step2")}</li>
        <li>{say("settings.claude.step3")}</li>
      </ol>
      <div className="settings-fields">
        <CopyField label={say("settings.claude.url")} value={here ? `${here}/mcp` : ""} />
        <CopyField label={say("settings.claude.client")} value={CLAUDE_CLIENT_ID} />
      </div>
      <Hint>
        <a className="settings-link" href="/auth/realms/arga/account">
          {say("settings.claude.sessions")}
        </a>
        {say("settings.claude.revoke")}
      </Hint>
    </Section>
  );
}

export function HomePanelsSettings({
  preferences,
  onChange,
}: {
  preferences: UiPreferences;
  onChange: (next: Partial<UiPreferences>) => void;
}) {
  const order = orderOf(preferences.home_panels?.order);
  const hidden: Set<string> = hiddenOf(preferences.home_panels);
  const save = (next: { order?: string[]; hidden?: string[] }) =>
    onChange({ home_panels: { order, hidden: [...hidden], ...next } });
  const move = (index: number, step: -1 | 1) => {
    const next = [...order];
    const to = index + step;
    if (to < 0 || to >= next.length) return;
    [next[index], next[to]] = [next[to]!, next[index]!];
    save({ order: next });
  };
  return (
    <Section title={say("settings.home")}>
      <ul className="settings-panels">
        {order.map((key, index) => {
          const area = AREAS.find((one) => one.key === key)!;
          return (
            <li key={key} className="settings-row">
              <Switch
                label={area.label}
                checked={!hidden.has(key)}
                onChange={(on) => save({ hidden: on ? [...hidden].filter((one) => one !== key) : [...hidden, key] })}
              />
              <IconButton icon="chevron-up" label={say("settings.home.up", { name: area.label })} size="small" variant="plain" disabled={index === 0} onClick={() => move(index, -1)} />
              <IconButton icon="chevron-down" label={say("settings.home.down", { name: area.label })} size="small" variant="plain" disabled={index === order.length - 1} onClick={() => move(index, 1)} />
            </li>
          );
        })}
      </ul>
      <Hint>{say("settings.home.hint")}</Hint>
    </Section>
  );
}
