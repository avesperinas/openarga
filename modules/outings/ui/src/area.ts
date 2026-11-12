import type { AreaView } from "@openarga/ui/area-map";

import { type Area, MAP_BASE, type Zone, readArea } from "./api";
import { useLoad } from "./Loads";

// TODO(ui): AreaMap still names its views after the first area; it should take the profile's boxes.
export const VIEW: Record<Zone, AreaView> = { near: "comarca", region: "navarra" };

export const mapBase = (area: Area) => `${MAP_BASE}${area.id}/`;

export function useArea(): Area | null {
  return useLoad("area", readArea).data;
}

export function useMapBase(): string | null {
  const area = useArea();
  return area?.map ? mapBase(area) : null;
}
