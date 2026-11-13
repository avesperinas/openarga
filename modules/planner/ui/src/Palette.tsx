import { CommandPalette, type IconName, type PaletteItem, dayStart, formatClock, matching } from "@openarga/ui";
import * as React from "react";

import { type Layer, type Occurrence, searchEvents } from "./api";
import { dateFormat, t } from "./lang";

export interface Command {
  id: string;
  label: string;
  icon: IconName;
  shortcut?: string;
  run: () => void;
}

interface Props {
  commands: Command[];
  layers: Map<string, Layer>;
  onOpen: (occurrence: Occurrence) => void;
  onClose: () => void;
}

const when = dateFormat({ weekday: "short", day: "numeric", month: "short", year: "numeric" });

export function describe(occurrence: Occurrence): string {
  const day = occurrence.all_day
    ? `${when.format(dayStart(occurrence.start))} · ${t("event.all_day")}`
    : `${when.format(new Date(occurrence.start))} · ${formatClock(new Date(occurrence.start))}`;
  return occurrence.location ? `${day} · ${occurrence.location}` : day;
}

export function Palette({ commands, layers, onOpen, onClose }: Props) {
  const [query, setQuery] = React.useState("");
  const [found, setFound] = React.useState<Occurrence[]>([]);
  const [searching, setSearching] = React.useState(false);

  React.useEffect(() => {
    const words = query.trim();
    if (words.length < 2) {
      setFound([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    let alive = true;
    const timer = setTimeout(() => {
      searchEvents(words)
        .then((result) => alive && setFound(result))
        .catch(() => alive && setFound([]))
        .finally(() => alive && setSearching(false));
    }, 180);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [query]);

  const events: PaletteItem[] = found.map((occurrence) => ({
    key: `e-${occurrence.id}`,
    label: occurrence.title,
    detail: describe(occurrence),
    tone: layers.get(occurrence.calendar_id)?.tone,
    icon: occurrence.original_start ? "repeat" : undefined,
    run: () => onOpen(occurrence),
  }));
  const actions: PaletteItem[] = matching(commands, query).map((command) => ({
    key: `c-${command.id}`,
    label: command.label,
    icon: command.icon,
    shortcut: command.shortcut,
    run: command.run,
  }));
  const words = query.trim();

  return (
    <CommandPalette
      label={t("palette.label")}
      placeholder={t("palette.placeholder")}
      query={query}
      onQuery={setQuery}
      onClose={onClose}
      empty={searching ? t("palette.searching") : t("palette.nothing", { words })}
      groups={[
        { label: t("palette.events"), items: events },
        { label: t("palette.commands"), items: actions },
      ]}
    />
  );
}
