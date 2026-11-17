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
import { t } from "./lang";

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
      <ScreenHeader title={kind === "plans" ? t("nav.plans") : t("nav.trips")} />
      <CreateButton label={t("trip.title")} onClick={() => navigate({ screen: "edit", id: null })} />
      {kind === "trips" && listed !== null && listed.length > 0 && (
        <div className="travel-actions">
          <Button variant="tinted" icon="play" onClick={() => navigate({ screen: "journey" })}>
            {t("trips.journey")}
          </Button>
        </div>
      )}

      {trips === null && problem && <ErrorState title={t("error.no_answer")} detail={problem} onRetry={onRetry} />}
      {trips === null && !problem && <Skeleton label={t("trips.loading")} />}
      {kind === "trips" && listed !== null && listed.length === 0 && (
        <EmptyState
          title={t("trips.empty")}
          action={{ label: t("stats.add_trip"), icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
        >
          {t("trips.empty_detail")}
        </EmptyState>
      )}
      {kind === "plans" && trips !== null && coming.length === 0 && ideas.length === 0 && (
        <EmptyState
          title={t("trips.no_plans")}
          action={{ label: t("today.plan_trip"), icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
        >
          {t("trips.no_plans_detail")}
        </EmptyState>
      )}

      {kind === "plans" && trips !== null && (
        <section className="travel-group">
          <GroupLabel>
            {t("trips.ideas")}
            <span className="travel-group-detail">{t("trips.ideas_detail")}</span>
          </GroupLabel>
          {ideaProblem && <Hint tone="warning">{ideaProblem}</Hint>}
          <div className="travel-cards">
            {ideas.map((one) => (
              <IdeaCard key={one.id} idea={one} navigate={navigate} />
            ))}
            <Button variant="tinted" icon="plus" onClick={() => setCreating(true)}>
              {t("trips.idea")}
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
              setIdeaProblem(error instanceof Error ? error.message : t("trips.error.idea"));
              setCreating(false);
            }
          }}
        />
      )}

      {kind === "plans" && coming.length > 0 && (
        <section className="travel-group">
          <GroupLabel>
            {t("trips.upcoming")}
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
            {t("trips.archived")} · {archived.length}
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
    idea.budget_eur !== null ? t("trips.per_person", { amount: euros(idea.budget_eur) }) : null,
  ].filter(Boolean);
  return (
    <button type="button" className="surface travel-card travel-idea-card" onClick={() => navigate({ screen: "idea", id: idea.id })}>
      <span className="travel-card-text">
        <span className="travel-card-title">{idea.title}</span>
        <span className="travel-card-detail">
          {idea.places.map((one) => one.place.name).join(" · ") || t("trips.no_places")}
        </span>
        {facts.length > 0 && <span className="travel-card-spend">{facts.join(" · ")}</span>}
        {idea.countries.length > 0 && (
          <span className="travel-card-flags" aria-label={t("trips.countries", { names: idea.countries.join(", ") })}>
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
          {trip.space_id !== null && ` · ${t("trip.shared")}`}
        </span>
        <span className="travel-card-flags" aria-label={t("trips.countries", { names: trip.countries.join(", ") })}>
          {trip.countries.map(flag).join(" ")}
        </span>
        {trip.spend.per_person > 0 && (
          <span className="travel-card-spend">
            {t("trips.per_person", { amount: euros(trip.spend.per_person) })}
            {trip.spend.per_day !== null && ` · ${t("trips.per_day", { amount: euros(trip.spend.per_day) })}`}
          </span>
        )}
      </span>
    </button>
  );
}
