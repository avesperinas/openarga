import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PositionsSheet } from "./Positions";
import { StatementSheet } from "./StatementSheet";
import type { ProductDetail } from "./api";
import { english, inLocale, spanish } from "./i18n/testing";

const product = { key: "main", name: "Brokerage" } as ProductDetail;

describe("the sheets of a product", () => {
  it("offers to pick a file in the person's language", () => {
    const en = renderToStaticMarkup(inLocale(<StatementSheet product={product} onBack={() => undefined} onImported={() => undefined} />, "en"));
    const es = renderToStaticMarkup(inLocale(<StatementSheet product={product} onBack={() => undefined} onImported={() => undefined} />, "es"));
    expect(en).toContain(english("statement.title", { name: "Brokerage" }));
    expect(en).toContain(english("statement.pick"));
    expect(es).toContain(spanish("statement.title", { name: "Brokerage" }));
    expect(es).toContain(spanish("statement.pick"));
    expect(es).not.toContain(english("statement.pick"));
  });

  it("shows the positions loading before the card arrives", () => {
    const en = renderToStaticMarkup(inLocale(<PositionsSheet product={product} onBack={() => undefined} onChanged={() => undefined} />, "en"));
    const es = renderToStaticMarkup(inLocale(<PositionsSheet product={product} onBack={() => undefined} onChanged={() => undefined} />, "es"));
    expect(en).toContain(english("positions.title", { name: "Brokerage" }));
    expect(en).toContain(english("positions.loading"));
    expect(es).toContain(spanish("positions.title", { name: "Brokerage" }));
    expect(es).toContain(spanish("positions.loading"));
  });
});
