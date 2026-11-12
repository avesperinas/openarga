import { BATCH, envelopeKey, parseEnvelopeKey, widgetUrl } from "../lib/envelope";
import { type Envelope, readCatalogue, readWidget } from "../lib/kernel";

export const dynamic = "force-dynamic";

const WIDGET_TIMEOUT_MS = 5000;

export async function GET(request: Request): Promise<Response> {
  const wanted = [...new Set(new URL(request.url).searchParams.getAll("w"))].slice(0, BATCH);
  const endpoints = new Map(
    (await readCatalogue()).map((entry) => [envelopeKey(entry.source, entry.id), entry.endpoint]),
  );
  const answers = await Promise.all(
    wanted.map(async (key): Promise<[string, Envelope | null]> => {
      const { widget, option } = parseEnvelopeKey(key);
      const endpoint = endpoints.get(widget);
      if (!endpoint) return [key, null];
      try {
        return [key, await readWidget(widgetUrl(endpoint, option), WIDGET_TIMEOUT_MS)];
      } catch {
        return [key, null];
      }
    }),
  );
  return Response.json(Object.fromEntries(answers), { headers: { "cache-control": "no-store" } });
}
