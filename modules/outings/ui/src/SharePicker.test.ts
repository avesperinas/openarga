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

describe("who a wish is shared with", () => {
  it("only yours, without a space", () => {
    const trip = { space_id: null, mine: true };
    expect(sharedTitle(trip, [casa])).toBe("Only yours");
    expect(sharedSubtitle(trip, [casa])).toBe("Only you see it");
  });

  it("shared by you, with who sees it", () => {
    const trip = { space_id: "casa", mine: true };
    expect(sharedTitle(trip, [casa])).toBe("Casa");
    expect(sharedSubtitle(trip, [casa])).toBe("Seen and edited by: You and Luis");
  });

  it("shared with you, said", () => {
    const trip = { space_id: "casa", mine: false };
    expect(sharedSubtitle(trip, [casa])).toBe("Seen and edited by: You and Luis. Shared with you");
  });

  it("with nobody else in the space", () => {
    expect(withWhom({ ...casa, members: [{ user_id: "ana", name: "Ana" }] })).toBe("Only you, for now");
  });
});
