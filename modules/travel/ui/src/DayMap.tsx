import { EmptyState, ErrorState, GroupLabel, Hint, Icon, Screen, SegmentedControl, Skeleton } from "@openarga/ui";
import { lazy, Suspense, useEffect, useState } from "react";

import { type DayRoute, type Profile, Unauthorised, readDayRoute, signIn } from "./api";
import type { Navigate } from "./App";
import { ScreenHeader } from "./Header";
import { dayLabel, distance, duration } from "./words";
import { t } from "./lang";

const StreetMap = lazy(() => import("@openarga/ui/street-map").then((found) => ({ default: found.StreetMap })));

const PROFILES: { value: Profile; readonly label: string }[] = (["foot", "bike", "car"] as const).map((value) => ({
  value,
  get label() {
    return t(`map.profile.${value}`);
  },
}));

export function DayMapScreen({ id, day, navigate }: { id: string; day: string; navigate: Navigate }) {
  const [profile, setProfile] = useState<Profile>("foot");
  const [route, setRoute] = useState<DayRoute | null>(null);
  const [problem, setProblem] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    readDayRoute(id, day, profile)
      .then((found) => current && setRoute(found))
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (current) setProblem(error instanceof Error ? error.message : t("day.error.read"));
      });
    return () => {
      current = false;
    };
  }, [id, day, profile]);

  const back = { label: t("days.title"), onClick: () => navigate({ screen: "days", id }) };
  const total =
    route && route.distance_m !== null && route.duration_s !== null
      ? `${distance(route.distance_m)} · ${duration(route.duration_s)}`
      : undefined;

  return (
    <Screen>
      <ScreenHeader eyebrow={dayLabel(day)} title={t("today.day_on_map")} back={back} />
      {problem && !route && (
        <ErrorState
          title={t("error.no_answer")}
          detail={problem}
          onRetry={() => {
            setProblem("");
            return readDayRoute(id, day, profile).then(setRoute, (error: unknown) =>
              setProblem(error instanceof Error ? error.message : t("day.error.read")),
            );
          }}
        />
      )}
      <SegmentedControl label={t("map.profile")} value={profile} onChange={setProfile} options={PROFILES} />
      {!route && !problem && <Skeleton label={t("today.loading")} />}
      {route && route.stops.length === 0 && (
        <EmptyState
          icon="map"
          title={t("day.empty")}
          action={{ label: t("day.go_days"), icon: "calendar", onClick: () => navigate({ screen: "days", id }) }}
        >
          {t("day.empty_detail")}
        </EmptyState>
      )}
      {route && route.stops.length > 0 && (
        <>
          <div className="surface travel-day-map">
            <Suspense fallback={<Skeleton label={t("map.loading")} />}>
              <StreetMap
                tiles="/api/travel/tiles/{z}/{x}/{y}"
                glyphs="/travel/map/"
                stops={route.stops}
                line={route.line}
                selected={selected}
                onSelect={setSelected}
                label={t("day.map_of", { day: dayLabel(day) })}
              />
            </Suspense>
          </div>
          {route.failed && <Hint tone="warning">{t("day.no_route", { reason: route.failed })}</Hint>}
          <section className="travel-group">
            <GroupLabel>
              {t("day.stops")}
              {total && <span className="travel-group-detail">{total}</span>}
            </GroupLabel>
            <ol className="surface travel-day">
              {route.stops.map((stop, index) => (
                <li
                  key={`${stop.id}-${index}`}
                  className="travel-block travel-route-stop"
                  data-selected={stop.id === selected || undefined}
                >
                  <button type="button" className="travel-block-body" onClick={() => setSelected(stop.id)}>
                    <span className="travel-route-number" data-home={stop.number === null || undefined}>
                      {stop.number === null ? <Icon name="home" /> : stop.number}
                    </span>
                    <span className="travel-step-text">
                      <span className="travel-step-title">{stop.title}</span>
                      {route.legs[index] && (
                        <span className="travel-step-detail">
                          {t("day.to_next")} {distance(route.legs[index]!.distance_m)} ·{" "}
                          {duration(route.legs[index]!.duration_s)}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </Screen>
  );
}
