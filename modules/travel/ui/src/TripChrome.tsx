import { Icon, type IconName } from "@openarga/ui";
import { useEffect, useRef } from "react";

import { type Trip, coverUrl } from "./api";
import type { Navigate, Route } from "./App";
import { lock } from "./tripApp";
import { PHASES, dateRange, flag, nights } from "./words";
import { plural, t } from "./lang";

export type TripTab = "today" | "trip" | "days" | "tripmap" | "bookings" | "money" | "notes" | "journal" | "tripsettings";

type Tab = { id: TripTab; readonly label: string; icon: IconName };

const tab = (id: TripTab, icon: IconName): Tab => ({
  id,
  icon,
  get label() {
    return t(`tab.${id}`);
  },
});

const TABS: Tab[] = [
  tab("trip", "home"),
  tab("days", "calendar"),
  tab("tripmap", "map"),
  tab("bookings", "ticket"),
  tab("money", "wallet"),
  tab("journal", "book"),
  tab("notes", "note"),
  tab("tripsettings", "settings"),
];
const TODAY = tab("today", "today");

export function TripTabs({
  id,
  active,
  navigate,
  today = false,
}: {
  id: string;
  active: TripTab;
  navigate: Navigate;
  today?: boolean;
}) {
  const tabs = today || (lock() === id && active === "today") ? [TODAY, ...TABS] : TABS;
  const bar = useRef<HTMLElement>(null);
  useEffect(() => {
    const current = bar.current?.querySelector<HTMLElement>('[aria-current="page"]');
    if (current && bar.current) bar.current.scrollLeft = current.offsetLeft - bar.current.clientWidth / 2 + current.clientWidth / 2;
  }, [active]);
  return (
    <nav ref={bar} className="travel-trip-tabs" aria-label={t("tab.sections")}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className="travel-trip-tab"
          aria-current={tab.id === active ? "page" : undefined}
          onClick={() =>
            tab.id !== active && navigate(tab.id === "today" ? { screen: "today" } : ({ screen: tab.id, id } as Route))
          }
        >
          <Icon name={tab.icon} />
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

export function TripHero({ trip, onCover }: { trip: Trip; onCover?: () => void }) {
  const url = coverUrl(trip);
  const credit = trip.cover?.page ? trip.cover : null;
  return (
    <figure className="travel-hero" data-empty={url ? undefined : true}>
      {url ? (
        <img className="travel-hero-image" src={url} alt="" />
      ) : (
        <span className="travel-hero-flags" aria-hidden>
          {trip.countries.map((code) => flag(code)).join(" ")}
        </span>
      )}
      <figcaption className="travel-hero-caption">
        <span className="travel-hero-phase">{PHASES[trip.phase]}</span>
        <span className="travel-hero-dates">
          {dateRange(trip.starts_on, trip.ends_on)} · {plural(trip.days, "count.days")} · {nights(trip.nights)}
        </span>
      </figcaption>
      {onCover && (
        <button type="button" className="travel-hero-edit glass" onClick={onCover} aria-label={t("cover.change")}>
          <Icon name="camera" />
        </button>
      )}
      {credit && (
        <a className="travel-hero-credit" href={credit.page!} target="_blank" rel="noreferrer">
          {[credit.author, credit.license].filter(Boolean).join(" · ") || "Wikimedia Commons"}
        </a>
      )}
    </figure>
  );
}
