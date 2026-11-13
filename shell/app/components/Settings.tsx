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

const THEMES: SegmentedOption<UiPreferences["theme"]>[] = [
  { value: "system", label: "Sistema", icon: "system" },
  { value: "light", label: "Claro", icon: "sun" },
  { value: "dark", label: "Oscuro", icon: "moon" },
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

      <Section title="Transparencia">
        <div className="settings-row">
          <Slider
            label="Transparencia del cristal"
            min={OPACITY_RANGE.min}
            max={OPACITY_RANGE.max}
            step={OPACITY_RANGE.step}
            value={preferences.glass_opacity}
            valueText={`${Math.round(preferences.glass_opacity * 100)} por ciento`}
            onChange={(glass_opacity) => onChange({ glass_opacity })}
          />
          <output className="settings-value">
            {Math.round(preferences.glass_opacity * 100)}%
          </output>
        </div>
        <Hint>
          {preferences.glass_opacity >= 1
            ? "Al máximo la barra es opaca y el desenfoque se apaga del todo."
            : "El efecto es inmediato y viaja al resto de tus dispositivos."}
        </Hint>
      </Section>

      <Section title="Tema">
        <SegmentedControl
          label="Tema"
          options={THEMES}
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
    <Section title="Iconos">
      <PreviewChoices
        label="Acabado de los iconos"
        value={preferences.icon_style ?? "solid"}
        onChange={(icon_style) => onChange({ icon_style })}
        options={ICON_STYLES.map((style) => ({
          ...style,
          preview: shown.map((module) => <img key={module.id} src={styledIcon(appIconOf(module)!, style.value)} alt="" />),
        }))}
      />
      <Hint>La app instalada en el móvil lleva siempre el de color: ese lo fija el sistema al instalarla.</Hint>
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
    <Section title="Nombres de las apps">
      <SelectField label="Nombres de las apps" hideLabel options={APP_NAME_SETS} value={set} onChange={choose} />
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
      <Hint>Es el nombre con el que salen en Módulos. Dentro de cada app sigue el de siempre.</Hint>
    </Section>
  );
}

export function Versions({ modules, platform }: { modules: ModuleSummary[]; platform?: string }) {
  const version = usePlatformVersion(platform);

  return (
    <Section title="Versiones">
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
      <Hint>
        Cada app se despliega por su cuenta: sus números no tienen por qué coincidir con el de arga.
      </Hint>
    </Section>
  );
}

export function ConnectClaude({ origin }: { origin?: string }) {
  const [here, setHere] = React.useState(origin ?? "");
  React.useEffect(() => {
    if (!origin) setHere(window.location.origin);
  }, [origin]);
  return (
    <Section title="Conectar Claude">
      <Hint>
        Conecta tu propio Claude a tu cuenta de arga. Lo que Claude consulte o
        haga, lo hace con tus datos y solo con los tuyos.
      </Hint>
      <ol className="settings-steps">
        <li>
          En Claude, abre Ajustes → Hub y añade un conector
          personalizado.
        </li>
        <li>
          Pega la URL del servidor. En las opciones avanzadas, pon el ID de
          cliente y deja el secreto vacío.
        </li>
        <li>Pulsa Conectar y entra con tu cuenta de Google.</li>
      </ol>
      <div className="settings-fields">
        <CopyField label="URL del servidor" value={here ? `${here}/mcp` : ""} />
        <CopyField label="ID de cliente" value={CLAUDE_CLIENT_ID} />
      </div>
      <Hint>
        <a className="settings-link" href="/auth/realms/arga/account">
          Ver tus sesiones y los accesos que has dado
        </a>
        , y quitarle el acceso a Claude cuando quieras.
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
    <Section title="Inicio">
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
              <IconButton icon="chevron-up" label={`Subir ${area.label}`} size="small" variant="plain" disabled={index === 0} onClick={() => move(index, -1)} />
              <IconButton icon="chevron-down" label={`Bajar ${area.label}`} size="small" variant="plain" disabled={index === order.length - 1} onClick={() => move(index, 1)} />
            </li>
          );
        })}
      </ul>
      <Hint>Cada panel encendido es una página del inicio, en este orden y delante de las de widgets. También se ponen y se quitan editando el inicio.</Hint>
    </Section>
  );
}
