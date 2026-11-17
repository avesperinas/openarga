import { missingKeys } from "@openarga/ui";

import { catalogs } from ".";

describe("the catalogs", () => {
  it("have the same keys in English and Spanish", () => {
    expect(missingKeys(catalogs)).toEqual([]);
  });
});
