import { AppHome, Button, dayKey, dayStart, GroupLabel, Hint, IconButton, MiniMonth, ToggleGroup, ToggleList, ToggleRow, useNow } from "@openarga/ui";
import * as React from "react";

import type { Layer } from "./api";
import { type AppGroup, shortName, sidebarGroups, usePreference } from "./data";
import { statusLine } from "./Subscribe";
import { t } from "./lang";

declare const __PLANNER_ICON__: string;

export const APP = { id: "planner", name: "Planner", icon: __PLANNER_ICON__ };

interface Props {
  layers: Layer[];
  range: string[];
  marked: Set<string>;
  today: string;
  onJump: (day: string) => void;
  onCreate: () => void;
  onToggle: (layer: Layer) => void;
  onEditLayer: (layer: Layer | null) => void;
  onSubscribe: () => void;
  onSettings: () => void;
}

export function Sidebar({
  layers,
  range,
  marked,
  today,
  onJump,
  onCreate,
  onToggle,
  onEditLayer,
  onSubscribe,
  onSettings,
}: Props) {
  const now = useNow(60_000);
  const [month, setMonth] = React.useState(() => `${(range[Math.floor(range.length / 2)] ?? today).slice(0, 7)}-01`);
  const middle = range[Math.floor(range.length / 2)] ?? today;
  React.useEffect(() => setMonth(`${middle.slice(0, 7)}-01`), [middle]);

  const groups = sidebarGroups(layers);
  const [opened, setOpened] = usePreference<string[]>("planner.sidebar.open", []);
  const toggleApp = (group: AppGroup) => {
    const shown = group.layers.filter((layer) => layer.visible).length;
    const show = shown < group.layers.length;
    for (const layer of group.layers) if (layer.visible !== show) onToggle(layer);
  };
  const row = (layer: Layer, name = layer.name, detail?: string) => (
    <ToggleRow
      key={layer.id}
      name={name}
      tone={layer.tone}
      detail={[layer.display === "background" ? t("layer.background_short") : null, detail].filter(Boolean).join(" · ") || undefined}
      checked={layer.visible}
      failing={layer.subscription?.failing}
      onChange={() => onToggle(layer)}
      action={{ icon: "edit", label: t("action.edit_named", { name: layer.name }), onClick: () => onEditLayer(layer) }}
    />
  );

  return (
    <div className="cr-sidebar-inner">
      <div className="cr-brand">
        <img className="app-logo" src={APP.icon} alt="" width="28" height="28" />
        <span className="cr-brand-name">Planner</span>
        <AppHome app="planner" className="cr-home" />
      </div>

      <Button variant="primary" icon="plus" block onClick={onCreate}>
        {t("event.new")}
      </Button>

      <MiniMonth
        month={month}
        range={range.length <= 7 ? range : []}
        marked={marked}
        weekNumbers
        onSelect={onJump}
        onMonthChange={(stepBy) => {
          const date = dayStart(month);
          date.setMonth(date.getMonth() + stepBy);
          setMonth(dayKey(date));
        }}
      />

      <div className="cr-layers-scroll">
        <section className="cr-layers" aria-label={t("side.mine")}>
          <header className="cr-section-head">
            <GroupLabel>{t("side.mine")}</GroupLabel>
            <IconButton icon="plus" label={t("layer.new")} size="small" variant="plain" onClick={() => onEditLayer(null)} />
          </header>
          <ToggleList>{groups.own.map((layer) => row(layer))}</ToggleList>
        </section>

        {groups.holidays.length > 0 && (
          <section className="cr-layers" aria-label={t("side.holidays")}>
            <header className="cr-section-head">
              <GroupLabel>{t("side.holidays")}</GroupLabel>
              <IconButton icon="settings" label={t("side.manage_subs")} size="small" variant="plain" onClick={onSubscribe} />
            </header>
            <ToggleList>
              {groups.holidays.map((layer) =>
                row(layer, layer.name, layer.origin === "subscription" ? statusLine(layer, now) : t("side.yours_by_hand")),
              )}
            </ToggleList>
            {groups.resting.length > 0 && <Hint>{t(groups.resting.length === 1 ? "side.resting.one" : "side.resting.other", { names: groups.resting.join(t("side.and")) })}</Hint>}
          </section>
        )}

        <section className="cr-layers" aria-label={t("subs.title")}>
          <header className="cr-section-head">
            <GroupLabel>{t("subs.title")}</GroupLabel>
            <IconButton icon="settings" label={t("side.manage_subs")} size="small" variant="plain" onClick={onSubscribe} />
          </header>
          {groups.subscriptions.length > 0 ? (
            <ToggleList>{groups.subscriptions.map((layer) => row(layer, layer.name, statusLine(layer, now)))}</ToggleList>
          ) : (
            <Button variant="plain" icon="globe" block onClick={onSubscribe}>
              {t("side.subscribe_hint")}
            </Button>
          )}
        </section>

        {groups.apps.length > 0 && (
          <section className="cr-layers" aria-label={t("side.apps")}>
            <header className="cr-section-head">
              <GroupLabel>{t("side.apps")}</GroupLabel>
            </header>
            <ToggleList>
              {groups.apps.map((group) => {
                if (group.layers.length === 1) return row(group.layers[0]!);
                const shown = group.layers.filter((layer) => layer.visible).length;
                const open = opened.includes(group.app);
                return (
                  <ToggleGroup
                    key={group.app}
                    name={group.name}
                    count={t("side.count", { shown, total: group.layers.length })}
                    tone={group.layers[0]?.tone}
                    state={shown === 0 ? "off" : shown === group.layers.length ? "on" : "mixed"}
                    onChange={() => toggleApp(group)}
                    open={open}
                    onOpen={(next) => setOpened(next ? [...opened, group.app] : opened.filter((one) => one !== group.app))}
                  >
                    {group.layers.map((layer) => row(layer, shortName(layer, group.name)))}
                  </ToggleGroup>
                );
              })}
            </ToggleList>
          </section>
        )}
      </div>

      <footer className="cr-sidebar-foot">
        <Button variant="plain" icon="settings" block onClick={onSettings}>
          {t("side.settings")}
        </Button>
      </footer>
    </div>
  );
}

