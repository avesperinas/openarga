import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { I18nProvider, createT, missingKeys, resolveLocale, useT } from "../src/i18n";

const catalogs = {
  en: { hello: "Hello, {name}", only: "Only in English" },
  es: { hello: "Hola, {name}" },
};

describe("i18n", () => {
  it("translates, fills variables and falls back to English and then to the key", () => {
    const t = createT(catalogs, "es");
    expect(t("hello", { name: "Alex" })).toBe("Hola, Alex");
    expect(t("only")).toBe("Only in English");
    expect(t("unknown.key")).toBe("unknown.key");
  });

  it("resolves the locale from the preference, then the browser, then English", () => {
    expect(resolveLocale("es-ES")).toBe("es");
    expect(resolveLocale("de")).toBe("en");
  });

  it("lists the keys a catalog is missing", () => {
    expect(missingKeys(catalogs)).toEqual([{ locale: "es", key: "only" }]);
  });

  it("gives components the translator of the provider", () => {
    function Greeting() {
      const t = useT();
      return <p>{t("hello", { name: "Sam" })}</p>;
    }
    const html = renderToStaticMarkup(
      <I18nProvider catalogs={catalogs} locale="es">
        <Greeting />
      </I18nProvider>,
    );
    expect(html).toBe("<p>Hola, Sam</p>");
  });
});
