import { localView, routeArc, useCountries } from "@openarga/ui/world-map";

import type { Trip } from "./api";
import { legsAround } from "./atlas";
import { GEO } from "./atlas";

const WIDTH = 120;
const HEIGHT = 80;
const PAD = 12;

export function MiniRoute({ trip }: { trip: Trip }) {
  const countries = useCountries(GEO);
  const stays = trip.stays
    .map((one) => one.place)
    .filter((place) => place.lon !== null && place.lat !== null)
    .map((place) => [place.lon!, place.lat!] as [number, number]);
  const arcs = legsAround(trip)
    .filter((leg) => [leg.from_place, leg.to_place].every((p) => p.lon !== null && p.lat !== null))
    .map((leg) => ({
      mode: leg.mode,
      points: routeArc([leg.from_place.lon!, leg.from_place.lat!], [leg.to_place.lon!, leg.to_place.lat!], leg.mode, 16)
        .coordinates as [number, number][],
    }));
  const view = localView([...stays, ...arcs.flatMap((one) => one.points)], WIDTH, HEIGHT, PAD);
  if (!view) return <div className="travel-mini-route travel-mini-route-empty" aria-hidden="true" />;

  const at = (point: [number, number]) => view.project(point) ?? [WIDTH / 2, HEIGHT / 2];

  return (
    <svg className="travel-mini-route" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true">
      {countries &&
        view.near(countries).map((country) => (
          <path key={country.properties.code} className="travel-mini-route-land" d={view.path(country) ?? ""} />
        ))}
      {arcs.map((line, index) => (
        <polyline
          key={index}
          className="travel-mini-route-line"
          data-mode={line.mode}
          points={line.points.map((point) => at(point).join(",")).join(" ")}
        />
      ))}
      {stays.map((stop, index) => {
        const [x, y] = at(stop);
        return <circle key={index} className="travel-mini-route-stop" cx={x} cy={y} r={3} />;
      })}
    </svg>
  );
}
