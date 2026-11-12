import { describe, expect, it } from "vitest";

import type { Place, Trip } from "./api";
import { itinerary } from "./TripScreen";

const place = (id: string, name: string): Place => ({
  id,
  name,
  display_name: null,
  lat: 50,
  lon: 3,
  country_code: "BE",
  region_code: "BE-VLG",
  country: null,
  region: null,
  kind: null,
});

describe("el itinerario", () => {
  it("cada trayecto antes del lugar al que llega, y las visitas dentro de su lugar", () => {
    const home = place("h", "Casa");
    const bruges = place("b", "Brujas");
    const ghent = place("g", "Gante");
    const trip = {
      starts_on: "2025-03-07",
      ends_on: "2025-03-10",
      stays: [
        { id: "s1", place: bruges, arrives_on: "2025-03-07", leaves_on: "2025-03-09", nights: 2, accommodation: null },
        { id: "s2", place: ghent, arrives_on: "2025-03-09", leaves_on: "2025-03-10", nights: 1, accommodation: null },
      ],
      visits: [{ id: "v1", place: place("d", "Damme"), stay_id: "s1", visited_on: "2025-03-08", note: null }],
      legs: [
        { id: "l2", from_place: bruges, to_place: ghent, mode: "train", travelled_on: null, km: 50, note: null },
        { id: "l1", from_place: home, to_place: bruges, mode: "plane", travelled_on: "2025-03-07", km: 1300, note: null },
      ],
    } as unknown as Trip;

    const steps = itinerary(trip).map((step) =>
      step.kind === "leg" ? `→${step.leg.to_place.name}` : step.kind === "stay" ? `${step.stay.place.name}(${step.visits.length})` : step.visit.place.name,
    );

    expect(steps).toEqual(["→Brujas", "Brujas(1)", "→Gante", "Gante(0)"]);
  });
});
