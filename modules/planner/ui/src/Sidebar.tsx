import { AppHome, Button, dayKey, dayStart, GroupLabel, Hint, IconButton, MiniMonth, ToggleGroup, ToggleList, ToggleRow, useNow } from "@openarga/ui";
import * as React from "react";

import type { Layer } from "./api";
import { type AppGroup, shortName, sidebarGroups, usePreference } from "./data";
import { statusLine } from "./Subscribe";

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
      detail={[layer.display === "background" ? "De fondo" : null, detail].filter(Boolean).join(" · ") || undefined}
      checked={layer.visible}
      failing={layer.subscription?.failing}
      onChange={() => onToggle(layer)}
      action={{ icon: "edit", label: `Editar ${layer.name}`, onClick: () => onEditLayer(layer) }}
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
        Nuevo evento
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
        <section className="cr-layers" aria-label="Mis calendarios">
          <header className="cr-section-head">
            <GroupLabel>Mis calendarios</GroupLabel>
            <IconButton icon="plus" label="Nueva capa" size="small" variant="plain" onClick={() => onEditLayer(null)} />
          </header>
          <ToggleList>{groups.own.map((layer) => row(layer))}</ToggleList>
        </section>

        {groups.holidays.length > 0 && (
          <section className="cr-layers" aria-label="Festivos">
            <header className="cr-section-head">
              <GroupLabel>Festivos</GroupLabel>
              <IconButton icon="settings" label="Suscripciones: añadir o quitar" size="small" variant="plain" onClick={onSubscribe} />
            </header>
            <ToggleList>
              {groups.holidays.map((layer) =>
                row(layer, layer.name, layer.origin === "subscription" ? statusLine(layer, now) : "Tuyos · a mano"),
              )}
            </ToggleList>
            {groups.resting.length > 0 && <Hint>{`${groups.resting.join(" y ")} ${groups.resting.length === 1 ? "libra" : "libran"} estos días`}</Hint>}
          </section>
        )}

        <section className="cr-layers" aria-label="Suscripciones">
          <header className="cr-section-head">
            <GroupLabel>Suscripciones</GroupLabel>
            <IconButton icon="settings" label="Suscripciones: añadir o quitar" size="small" variant="plain" onClick={onSubscribe} />
          </header>
          {groups.subscriptions.length > 0 ? (
            <ToggleList>{groups.subscriptions.map((layer) => row(layer, layer.name, statusLine(layer, now)))}</ToggleList>
          ) : (
            <Button variant="plain" icon="globe" block onClick={onSubscribe}>
              Festivos, partidos, carreras o un .ics, que se actualizan solos
            </Button>
          )}
        </section>

        {groups.apps.length > 0 && (
          <section className="cr-layers" aria-label="De tus apps">
            <header className="cr-section-head">
              <GroupLabel>De tus apps</GroupLabel>
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
                    count={`${shown} de ${group.layers.length}`}
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
          Ajustes
        </Button>
      </footer>
    </div>
  );
}

