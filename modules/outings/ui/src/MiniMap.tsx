import type { AreaPoint } from "@openarga/ui/area-map";
import { Suspense, lazy } from "react";

import { useMapBase } from "./area";

const AreaMap = lazy(() => import("@openarga/ui/area-map").then((found) => ({ default: found.AreaMap })));

export function MiniMap({ point, label }: { point: AreaPoint; label: string }) {
  const base = useMapBase();
  if (!base) return null;
  return (
    <div className="outings-mini-map">
      <Suspense fallback={null}>
        <AreaMap base={base} view="comarca" center={[point.lon, point.lat]} compact points={[point]} label={label} />
      </Suspense>
    </div>
  );
}
