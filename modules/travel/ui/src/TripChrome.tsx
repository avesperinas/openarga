import { Icon, type IconName } from "@openarga/ui";
import { useEffect, useRef } from "react";

import { type Trip, coverUrl } from "./api";
import type { Navigate, Route } from "./App";
import { lock } from "./tripApp";
import { PHASES, dateRange, flag, nights } from "./words";

export type TripTab = "today" | "trip" | "days" | "tripmap" | "bookings" | "money" | "notes" | "journal" | "tripsettings";

const TABS: { id: TripTab; label: string; icon: IconName }[] = [
  { id: "trip", label: "Resumen", icon: "home" },
  { id: "days", label: "Días", icon: "calendar" },
  { id: "tripmap", label: "Mapa", icon: "map" },
  { id: "bookings", label: "Reservas", icon: "ticket" },
  { id: "money", label: "Dinero", icon: "wallet" },
  { id: "journal", label: "Diario", icon: "book" },
  { id: "notes", label: "Notas", icon: "note" },
  { id: "tripsettings", label: "Ajustes", icon: "settings" },
];
const TODAY: { id: TripTab; label: string; icon: IconName } = { id: "today", label: "Hoy", icon: "today" };

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
    <nav ref={bar} className="travel-trip-tabs" aria-label="Secciones del viaje">
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
          {dateRange(trip.starts_on, trip.ends_on)} · {trip.days} días · {nights(trip.nights)}
        </span>
      </figcaption>
      {onCover && (
        <button type="button" className="travel-hero-edit glass" onClick={onCover} aria-label="Cambiar la portada">
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
