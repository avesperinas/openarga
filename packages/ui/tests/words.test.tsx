import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { missingKeys } from "../src/i18n";
import { configureRegional } from "../src/regional";
import { ErrorState, OfflineNotice } from "../src/states";
import es from "../src/i18n/es.json";
import { PLATFORM_CATALOGS, say } from "../src/words";

afterEach(() => configureRegional({ locale: "es-ES" }));

describe("platform words", () => {
  it("every key is in both catalogs", () => {
    expect(missingKeys(PLATFORM_CATALOGS)).toEqual([]);
  });

  it("follow the person's language", () => {
    configureRegional({ locale: "en-US" });
    expect(say("offline.pending.other", { count: 3 })).toBe("3 changes waiting to be sent.");
    expect(renderToStaticMarkup(<ErrorState onRetry={() => undefined} />)).toContain("Try again");
    expect(renderToStaticMarkup(<OfflineNotice offline />)).toContain("Offline");

    configureRegional({ locale: "es-ES" });
    expect(say("offline.pending.one")).toBe(es["offline.pending.one"]);
    expect(renderToStaticMarkup(<ErrorState onRetry={() => undefined} />)).toContain(es["error_state.retry"]);
  });

  it("fall back to English for a language without a catalog", () => {
    configureRegional({ locale: "de-DE" });
    expect(say("error_state.title")).toBe("Could not load");
  });
});
