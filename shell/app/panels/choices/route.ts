import { launchable, readArea, readModules } from "../../lib/kernel";
import { AREAS, type AreaKey } from "../../lib/panels";

export const dynamic = "force-dynamic";

const PANEL_TIMEOUT_MS = 6000;

export async function GET(request: Request): Promise<Response> {
  const area = new URL(request.url).searchParams.get("area") ?? "";
  if (!AREAS.some((one) => one.key === area)) return Response.json({ detail: "no hay esa área" }, { status: 404 });
  const found = await readArea(area as AreaKey, launchable(await readModules()), PANEL_TIMEOUT_MS);
  const choices = found.flatMap((one) =>
    (one.panel.tabs ?? []).map((tab) => ({ value: `${one.source}.${tab.id}`, label: `${one.name} · ${tab.label}` })),
  );
  return Response.json(choices, { headers: { "cache-control": "no-store" } });
}
