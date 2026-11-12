import { launchable, readArea, readModules } from "../lib/kernel";
import { AREAS, type AreaKey } from "../lib/panels";

export const dynamic = "force-dynamic";

const PANEL_TIMEOUT_MS = 6000;

const isArea = (value: string): value is AreaKey => AREAS.some((area) => area.key === value);

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const modules = launchable(await readModules());
  const wanted = params.get("all") ? AREAS.map((area) => area.key) : [params.get("area") ?? ""].filter(isArea);
  if (wanted.length === 0) return Response.json({ detail: "no hay esa área" }, { status: 404 });
  const found = await Promise.all(wanted.map(async (area) => [area, await readArea(area, modules, PANEL_TIMEOUT_MS)] as const));
  return Response.json({ areas: Object.fromEntries(found) }, { headers: { "cache-control": "no-store" } });
}
