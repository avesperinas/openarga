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
import { say } from "../words";

type Tab = "modules" | "settings";

const DESTINATIONS: { id: Tab | null; label: string; icon: IconName }[] = [
  { id: null, get label() { return say("tabs.today"); }, icon: "today" },
  { id: "modules", get label() { return say("tabs.modules"); }, icon: "modules" },
  { id: "settings", get label() { return say("tabs.settings"); }, icon: "settings" },
];

export function TabBar({ modules }: { modules: ModuleSummary[] }) {
  const [open, setOpen] = React.useState<Tab | null>(null);
  const [searching, setSearching] = React.useState(false);
  const desktop = useDesktop();
  const named = React.useMemo(
    () =>
      modules
        .filter((module) => !desktop?.preferences.hidden_apps?.includes(module.id))
        .map((module) => ({ ...module, name: appNameOf(module.id, module.name, desktop?.preferences) })),
    [modules, desktop?.preferences],
  );

  React.useEffect(() => {
    const follow = () => {
      if (window.location.hash !== "#settings") return;
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
        <nav className="glass tabbar" aria-label={say("tabs.sections")}>
          {DESTINATIONS.map((destination) => (
            <button
              key={destination.id ?? "today"}
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
            <span className="tab-label">{say("tabs.edit")}</span>
          </button>
        </nav>
      )}

      {open === "modules" && (
        <Overlay label={say("tabs.modules")} wide onClose={() => setOpen(null)}>
          <Launcher modules={named} iconStyle={desktop?.preferences.icon_style} search={<SearchField onOpen={() => setSearching(true)} />} />
        </Overlay>
      )}

      {open === "settings" && desktop && (
        <Overlay label={say("tabs.settings")} onClose={() => setOpen(null)}>
          <Settings preferences={desktop.preferences} onChange={desktop.change} modules={modules} locale={desktop.person.locale} />
        </Overlay>
      )}

      {searching && <SearchPalette modules={named} onClose={() => setSearching(false)} />}
    </>
  );
}
