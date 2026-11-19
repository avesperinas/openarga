"use client";

import { CommandPalette, Icon, type PaletteGroup, useShortcut } from "@openarga/ui";
import * as React from "react";

import type { ModuleSummary } from "../lib/kernel";
import { type FoundIn, appMatches, searchApps } from "../lib/search";
import { say } from "../words";

const PAUSE_MS = 200;

const go = (href: string) => () => window.location.assign(href);

export function searchGroups(modules: ModuleSummary[], query: string, found: FoundIn[]): PaletteGroup[] {
  const named = new Map(modules.map((module) => [module.id, module.name]));
  const apps = appMatches(modules, query).map((module) => ({
    key: `app:${module.id}`,
    label: module.name,
    detail: say("search.open"),
    icon: "modules" as const,
    run: go(module.view ?? module.api_prefix),
  }));
  return [
    { label: "Apps", items: apps },
    ...found.map((group) => ({
      label: named.get(group.app) ?? group.name,
      items: group.results.map((one, index) => ({
        key: `${group.app}:${index}:${one.href}`,
        label: one.title,
        detail: one.detail,
        run: go(one.href),
      })),
    })),
  ];
}

function useFound(query: string): FoundIn[] {
  const [found, setFound] = React.useState<FoundIn[]>([]);
  React.useEffect(() => {
    const wanted = query.trim();
    if (wanted.length < 2) {
      setFound([]);
      return;
    }
    const stop = new AbortController();
    const timer = setTimeout(() => {
      searchApps(wanted, stop.signal)
        .then((groups) => {
          if (!stop.signal.aborted) setFound(groups);
        })
        .catch(() => undefined);
    }, PAUSE_MS);
    return () => {
      clearTimeout(timer);
      stop.abort();
    };
  }, [query]);
  return found;
}

export function SearchPalette({ modules, onClose }: { modules: ModuleSummary[]; onClose: () => void }) {
  const [query, setQuery] = React.useState("");
  const found = useFound(query);
  return (
    <CommandPalette
      label={say("search.label")}
      placeholder={say("search.label")}
      query={query}
      onQuery={setQuery}
      groups={searchGroups(modules, query, found)}
      empty={query.trim() ? say("search.none") : say("search.hint")}
      onClose={onClose}
    />
  );
}

export function SearchField({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      className="launcher-search"
      onClick={onOpen}
      title={say("search.shortcut")}
    >
      <Icon name="search" />
      <span className="launcher-search-text">{say("search.label")}</span>
      <kbd className="launcher-search-key">⌘K</kbd>
    </button>
  );
}

export function useSearchShortcut(onOpen: () => void): void {
  useShortcut("k", onOpen);
}
