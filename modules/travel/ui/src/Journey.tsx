import { IconButton } from "@openarga/ui";
import { TimeBar, WorldMap } from "@openarga/ui/world-map";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Place, Trip } from "./api";
import type { Navigate } from "./App";
import { areasOf, listed, placesOf, playOrder, pointsOf, routesOf, year, yearSpan } from "./atlas";
import { GEO } from "./atlas";
import { dateRange } from "./words";

export function JourneyScreen({
  trips,
  home,
  navigate,
}: {
  trips: Trip[] | null;
  home: Place | null;
  navigate: Navigate;
}) {
  const all = useMemo(() => listed(trips ?? []), [trips]);
  const [years, setYears] = useState<[number, number]>(() => yearSpan(all));
  const [playing, setPlaying] = useState<number | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!trips || started.current) return;
    started.current = true;
    setYears(yearSpan(all));
    if (all.length) setPlaying(0);
  }, [trips, all]);

  const shown = useMemo(
    () => all.filter((one) => year(one.starts_on) >= years[0] && year(one.starts_on) <= years[1]),
    [all, years],
  );
  const order = useMemo(() => playOrder(shown), [shown]);
  const visible = playing === null ? shown : order.slice(0, playing + 1);
  const current = playing === null ? null : (order[playing] ?? null);

  const next = useCallback(
    () => setPlaying((now) => (now === null || now >= order.length - 1 ? null : now + 1)),
    [order.length],
  );
  const focus = useMemo(() => (current ? pointsOf(current) : null), [current]);

  const areas = useMemo(() => areasOf(visible, "country", [], home), [visible, home]);
  const places = useMemo(() => placesOf(visible), [visible]);
  const routes = useMemo(() => routesOf(visible), [visible]);
  const [min, max] = yearSpan(all);

  return (
    <main className="travel-map-screen">
      <WorldMap
        geoBase={GEO}
        level="country"
        areas={areas}
        places={places}
        routes={routes}
        highlight={current?.id ?? null}
        focus={focus}
        tour={current !== null}
        onTourDone={next}
        selected={null}
        label="El recorrido de los viajes"
      />

      <div className="travel-journey-top">
        <div className="travel-map-filter glass">
          <IconButton
            icon="chevron-left"
            label="Volver a los viajes"
            variant="plain"
            onClick={() => navigate({ screen: "trips" })}
          />
        </div>
      </div>

      <div className="travel-map-bottom">
        {current && (
          <p className="travel-map-playing glass" aria-live="polite">
            <span className="travel-map-chosen-title">{current.title}</span>
            <span className="travel-map-chosen-detail">{dateRange(current.starts_on, current.ends_on)}</span>
          </p>
        )}
        {all.length > 0 && (
          <TimeBar
            min={min}
            max={max}
            value={years}
            onChange={(next) => {
              setPlaying(null);
              setYears(next);
            }}
            playing={playing !== null}
            onPlay={() => order.length && setPlaying(0)}
            onPause={() => setPlaying(null)}
          />
        )}
      </div>
    </main>
  );
}
