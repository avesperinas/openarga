import { describe, expect, it } from "vitest";

import type { Space } from "./api";
import { sharedSubtitle, sharedTitle, withWhom } from "./SharePicker";

const casa: Space = {
  id: "casa",
  name: "Casa",
  me: "ana",
  members: [
    { user_id: "ana", name: "Ana" },
    { user_id: "luis", name: "Luis" },
  ],
};

describe("con quién se comparte un viaje", () => {
  it("solo tuyo, sin espacio", () => {
    const trip = { space_id: null, mine: true };
    expect(sharedTitle(trip, [casa])).toBe("Solo tuyo");
    expect(sharedSubtitle(trip, [casa])).toBe("Solo lo ves tú");
  });

  it("compartido por ti, con quién lo ve", () => {
    const trip = { space_id: "casa", mine: true };
    expect(sharedTitle(trip, [casa])).toBe("Casa");
    expect(sharedSubtitle(trip, [casa])).toBe("Lo ven y lo editan: Tú y Luis");
  });

  it("compartido contigo, dicho", () => {
    const trip = { space_id: "casa", mine: false };
    expect(sharedSubtitle(trip, [casa])).toBe("Lo ven y lo editan: Tú y Luis. Te lo compartieron");
  });

  it("sin nadie más en el espacio", () => {
    expect(withWhom({ ...casa, members: [{ user_id: "ana", name: "Ana" }] })).toBe("Solo tú, de momento");
  });
});
