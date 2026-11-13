import type { AreaViews, Box } from "@openarga/ui/area-map";

import { type Area, MAP_BASE, readArea } from "./api";
import { useLoad } from "./Loads";

export interface AreaMapSetup {
  base: string;
  views: AreaViews;
  reliefCredit?: string;
}

const box = ([west, south, east, north]: Area["near_box"]): Box => [
  [west, south],
  [east, north],
];

export function mapOf(area: Area): AreaMapSetup | null {
  if (!area.map) return null;
  return {
    base: `${MAP_BASE}${area.id}/`,
    views: { near: box(area.near_box), region: box(area.region_box) },
    reliefCredit: area.relief ?? undefined,
  };
}

export function useArea(): Area | null {
  return useLoad("area", readArea).data;
}

export function useAreaMap(): AreaMapSetup | null {
  const area = useArea();
  return area ? mapOf(area) : null;
}
