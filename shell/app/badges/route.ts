import { launchable, readBadge, readModules } from "../lib/kernel";

export const dynamic = "force-dynamic";

const BADGE_TIMEOUT_MS = 5000;

export async function GET(): Promise<Response> {
  const modules = launchable(await readModules()).filter((module) => module.badge);
  const answers = await Promise.all(
    modules.map(async (module) => [module.id, await readBadge(module.badge!, BADGE_TIMEOUT_MS)] as const),
  );
  return Response.json(Object.fromEntries(answers.filter(([, count]) => count !== null)), {
    headers: { "cache-control": "no-store" },
  });
}
