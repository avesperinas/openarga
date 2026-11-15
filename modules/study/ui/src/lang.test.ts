import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { CATALOGS, setLocale, t } from "./lang";
import { grade } from "./words";

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    expect([t("action.save"), grade(6.25)]).toEqual(["Save", "6.3"]);
    setLocale("es");
    expect([t("action.save"), grade(6.25)]).toEqual([CATALOGS.es!["action.save"], "6,3"]);
  });
});
