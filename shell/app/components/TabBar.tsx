"use client";

import { Icon, type IconName } from "@openarga/ui";
import * as React from "react";

import type { ModuleSummary } from "../lib/kernel";
import { appNameOf } from "../lib/preferences";
import { useDesktop } from "./Desktop";
import { Launcher } from "./Launcher";
import { Overlay } from "./Overlay";
import { SearchField, SearchPalette, useSearchShortcut } from "./Search";
import { Settings } from "./Settings";

type Tab = "modules" | "settings";

const DESTINATIONS: { id: Tab | null; label: string; icon: IconName }[] = [
  { id: null, label: "Hoy", icon: "today" },
  { id: "modules", label: "Módulos", icon: "modules" },
  { id: "settings", label: "Ajustes", icon: "settings" },
];

export function TabBar({ modules }: { modules: ModuleSummary[] }) {
  const [open, setOpen] = React.useState<Tab | null>(null);
  const [searching, setSearching] = React.useState(false);
  const desktop = useDesktop();
  const named = React.useMemo(
    () => modules.map((module) => ({ ...module, name: appNameOf(module.id, module.name, desktop?.preferences) })),
    [modules, desktop?.preferences],
  );

  React.useEffect(() => {
    const follow = () => {
      if (window.location.hash !== "#ajustes") return;
      setOpen("settings");
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    };
    follow();
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
  }, []);

  useSearchShortcut(() => setSearching(true));

  const edit = () => {
    setOpen(null);
    desktop?.setEditing(true);
  };

  return (
    <>
      {!desktop?.editing && (
        <nav className="glass tabbar" aria-label="Secciones">
          {DESTINATIONS.map((destination) => (
            <button
              key={destination.label}
              type="button"
              className="tab"
              data-active={open === destination.id || undefined}
              aria-current={destination.id === null ? open === null : undefined}
              aria-expanded={destination.id === null ? undefined : open === destination.id}
              onClick={() => setOpen(destination.id)}
            >
              <Icon name={destination.icon} />
              <span className="tab-label">{destination.label}</span>
            </button>
          ))}
          <button type="button" className="tab" onClick={edit}>
            <Icon name="edit" />
            <span className="tab-label">Editar</span>
          </button>
        </nav>
      )}

      {open === "modules" && (
        <Overlay label="Módulos" wide onClose={() => setOpen(null)}>
          <Launcher modules={named} iconStyle={desktop?.preferences.icon_style} search={<SearchField onOpen={() => setSearching(true)} />} />
        </Overlay>
      )}

      {open === "settings" && desktop && (
        <Overlay label="Ajustes" onClose={() => setOpen(null)}>
          <Settings preferences={desktop.preferences} onChange={desktop.change} modules={modules} />
        </Overlay>
      )}

      {searching && <SearchPalette modules={named} onClose={() => setSearching(false)} />}
    </>
  );
}
