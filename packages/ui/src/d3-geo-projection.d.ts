declare module "d3-geo-projection" {
  import type { GeoProjection } from "d3-geo";

  export function geoProject<T>(object: T, projection: GeoProjection): T;
}

declare module "*?worker&url" {
  const url: string;
  export default url;
}
