import { Button, CreateButton, EmptyState, ErrorState, GroupLabel, Hint, Screen, Skeleton } from "@openarga/ui";
import { useState } from "react";

import { type Idea, type OtherPlace, type Place, type Trip, createIdea } from "./api";
import type { Navigate } from "./App";
import { AppVersion } from "./AppVersion";
import { ahead, listed as inList, lived, year } from "./atlas";
import { ScreenHeader } from "./Header";
import { HomePlace } from "./Home";
import { IdeaSheet } from "./IdeaSheet";
import { later } from "./Later";
import { OtherPlaces } from "./OtherPlaces";
const MiniRoute = later(() => import("./MiniRoute").then((found) => found.MiniRoute), { screen: false, rows: 1 });

import { PHASES, dateRange, daysRange, euros, flag, monthsLabel, nights, trips as tripsWord } from "./words";

export function TripsScreen({
  kind,
  trips,
  ideas,
  others,
  home,
  problem,
  onRetry,
  navigate,
  onChanged,
}: {
  kind: "plans" | "trips";
  trips: Trip[] | null;
  ideas: Idea[];
  others: OtherPlace[];
  home: Place | null;
  problem: string;
  onRetry: () => Promise<void>;
  navigate: Navigate;
  onChanged: () => void;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [ideaProblem, setIdeaProblem] = useState("");
  const archived = (trips ?? []).filter((one) => one.archived);
  const coming = trips === null ? [] : ahead(trips);
  const listed = trips === null ? null : inList(lived(trips).filter((one) => one.phase === "done"));
  const years = new Map<number, Trip[]>();
  for (const one of listed ?? []) {
    const found = years.get(year(one.starts_on)) ?? [];
    found.push(one);
    years.set(year(one.starts_on), found);
  }

  return (
    <Screen>
      <ScreenHeader title={kind === "plans" ? "Planes" : "Viajes"} />
      <CreateButton label="Viaje" onClick={() => navigate({ screen: "edit", id: null })} />
      {kind === "trips" && listed !== null && listed.length > 0 && (
        <div className="travel-actions">
          <Button variant="tinted" icon="play" onClick={() => navigate({ screen: "journey" })}>
            Ver el recorrido
          </Button>
        </div>
      )}

      {trips === null && problem && <ErrorState title="Travel no contesta" detail={problem} onRetry={onRetry} />}
      {trips === null && !problem && <Skeleton label="Cargando los viajes" />}
      {kind === "trips" && listed !== null && listed.length === 0 && (
        <EmptyState
          title="Aún no hay viajes hechos"
          action={{ label: "Añadir un viaje", icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
        >
          Añade uno con sus sitios, sus trayectos y lo que costó, o cuéntaselo a Claude: busca los lugares él mismo y lo
          deja en el mapa.
        </EmptyState>
      )}
      {kind === "plans" && trips !== null && coming.length === 0 && ideas.length === 0 && (
        <EmptyState
          title="Sin planes"
          action={{ label: "Planear un viaje", icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
        >
          Lo que tienes por delante sale aquí: un viaje con fechas, o una idea para cuando sea.
        </EmptyState>
      )}

      {kind === "plans" && trips !== null && (
        <section className="travel-group">
          <GroupLabel>
            Ideas
            <span className="travel-group-detail">Viajes que quieres hacer, aún sin fechas</span>
          </GroupLabel>
          {ideaProblem && <Hint tone="warning">{ideaProblem}</Hint>}
          <div className="travel-cards">
            {ideas.map((one) => (
              <IdeaCard key={one.id} idea={one} navigate={navigate} />
            ))}
            <Button variant="tinted" icon="plus" onClick={() => setCreating(true)}>
              Idea
            </Button>
          </div>
        </section>
      )}
      {creating && (
        <IdeaSheet
          idea={null}
          onClose={() => setCreating(false)}
          onSave={async (data) => {
            try {
              const made = await createIdea(data);
              onChanged();
              navigate({ screen: "idea", id: made.id });
            } catch (error) {
              setIdeaProblem(error instanceof Error ? error.message : "No se ha podido crear la idea.");
              setCreating(false);
            }
          }}
        />
      )}

      {kind === "plans" && coming.length > 0 && (
        <section className="travel-group">
          <GroupLabel>
            Próximos
            <span className="travel-group-detail">{tripsWord(coming.length)}</span>
          </GroupLabel>
          <div className="travel-cards">
            {coming.map((one) => (
              <TripCard key={one.id} trip={one} navigate={navigate} />
            ))}
          </div>
        </section>
      )}

      {kind === "trips" && [...years.entries()].map(([when, list]) => (
        <section key={when} className="travel-group">
          <GroupLabel>
            {when}
            <span className="travel-group-detail">
              {tripsWord(list.length)} · {nights(list.reduce((sum, one) => sum + one.nights, 0))}
            </span>
          </GroupLabel>
          <div className="travel-cards">
            {list.map((one) => (
              <TripCard key={one.id} trip={one} navigate={navigate} />
            ))}
          </div>
        </section>
      ))}
      {kind === "trips" && trips !== null && <OtherPlaces others={others} onChanged={onChanged} />}
      {kind === "trips" && trips !== null && <HomePlace home={home} onChanged={onChanged} />}
      {kind === "trips" && archived.length > 0 && (
        <section className="travel-archived">
          <Button
            variant="plain"
            size="small"
            aria-expanded={showArchived}
            onClick={() => setShowArchived(!showArchived)}
          >
            Archivados · {archived.length}
          </Button>
          {showArchived && (
            <div className="travel-cards">
              {archived.map((one) => (
                <TripCard key={one.id} trip={one} navigate={navigate} />
              ))}
            </div>
          )}
        </section>
      )}
      <AppVersion />
    </Screen>
  );
}

function IdeaCard({ idea, navigate }: { idea: Idea; navigate: Navigate }) {
  const facts = [
    idea.months.length ? monthsLabel(idea.months) : null,
    daysRange(idea.days_min, idea.days_max),
    idea.budget_eur !== null ? `${euros(idea.budget_eur)} por persona` : null,
  ].filter(Boolean);
  return (
    <button type="button" className="surface travel-card travel-idea-card" onClick={() => navigate({ screen: "idea", id: idea.id })}>
      <span className="travel-card-text">
        <span className="travel-card-title">{idea.title}</span>
        <span className="travel-card-detail">
          {idea.places.map((one) => one.place.name).join(" · ") || "Sin destinos aún"}
        </span>
        {facts.length > 0 && <span className="travel-card-spend">{facts.join(" · ")}</span>}
        {idea.countries.length > 0 && (
          <span className="travel-card-flags" aria-label={`Países: ${idea.countries.join(", ")}`}>
            {idea.countries.map(flag).join(" ")}
          </span>
        )}
      </span>
    </button>
  );
}

function TripCard({ trip, navigate }: { trip: Trip; navigate: Navigate }) {
  return (
    <button type="button" className="surface travel-card" onClick={() => navigate({ screen: "trip", id: trip.id })}>
      <MiniRoute trip={trip} />
      <span className="travel-card-text">
        <span className="travel-card-title">{trip.title}</span>
        <span className="travel-card-detail">
          {trip.phase !== "done" && `${PHASES[trip.phase]} · `}
          {dateRange(trip.starts_on, trip.ends_on)} · {nights(trip.nights)}
          {trip.space_id !== null && " · Compartido"}
        </span>
        <span className="travel-card-flags" aria-label={`Países: ${trip.countries.join(", ")}`}>
          {trip.countries.map(flag).join(" ")}
        </span>
        {trip.spend.per_person > 0 && (
          <span className="travel-card-spend">
            {euros(trip.spend.per_person)} por persona
            {trip.spend.per_day !== null && ` · ${euros(trip.spend.per_day)}/día`}
          </span>
        )}
      </span>
    </button>
  );
}
