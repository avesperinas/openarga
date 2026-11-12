import { launchable, readModules, readSearch } from "../lib/kernel";
import { type FoundIn, PER_APP, readFound } from "../lib/search";

export const dynamic = "force-dynamic";

const SEARCH_TIMEOUT_MS = 2500;
const LONGEST = 200;

export async function GET(request: Request): Promise<Response> {
  const query = (new URL(request.url).searchParams.get("q") ?? "").trim().slice(0, LONGEST);
  if (query.length < 2) return Response.json({ groups: [] }, { headers: { "cache-control": "no-store" } });

  const modules = launchable(await readModules()).filter((module) => module.search);
  const answers = await Promise.all(
    modules.map(async (module): Promise<FoundIn> => ({
      app: module.id,
      name: module.name,
      results: readFound(await readSearch(module.search!, query, PER_APP, SEARCH_TIMEOUT_MS)),
    })),
  );
  return Response.json(
    { groups: answers.filter((group) => group.results.length > 0) },
    { headers: { "cache-control": "no-store" } },
  );
}
