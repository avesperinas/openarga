import type { AreaPoint } from "@openarga/ui/area-map";
import { Suspense, lazy } from "react";

import { useAreaMap } from "./area";

const AreaMap = lazy(() => import("@openarga/ui/area-map").then((found) => ({ default: found.AreaMap })));

export function MiniMap({ point, label }: { point: AreaPoint; label: string }) {
  const setup = useAreaMap();
  if (!setup) return null;
  return (
    <div className="outings-mini-map">
      <Suspense fallback={null}>
        <AreaMap {...setup} view="near" center={[point.lon, point.lat]} compact points={[point]} label={label} />
      </Suspense>
    </div>
  );
}
