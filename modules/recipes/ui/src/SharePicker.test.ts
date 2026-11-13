import { describe, expect, it } from "vitest";

import { english as t } from "./i18n/testing";
import type { Space } from "./api";
import { sharedSubtitle, sharedTitle, withWhom } from "./SharePicker";

const home: Space = {
  id: "home",
  name: "Home",
  me: "ana",
  members: [
    { user_id: "ana", name: "Ana" },
    { user_id: "luis", name: "Luis" },
  ],
};

describe("who a recipe is shared with", () => {
  it("only yours, without a space", () => {
    const recipe = { space_id: null, mine: true };
    expect(sharedTitle(recipe, [home], t)).toBe("Only yours");
    expect(sharedSubtitle(recipe, [home], t)).toBe("Only you see it");
  });

  it("shared by you, with who sees it", () => {
    const recipe = { space_id: "home", mine: true };
    expect(sharedTitle(recipe, [home], t)).toBe("Home");
    expect(sharedSubtitle(recipe, [home], t)).toBe("They see it and cook it: You and Luis");
  });

  it("shared with you, said", () => {
    const recipe = { space_id: "home", mine: false };
    expect(sharedSubtitle(recipe, [home], t)).toBe("They see it and cook it: You and Luis. Someone shared it with you");
  });

  it("with nobody else in the space", () => {
    expect(withWhom({ ...home, members: [{ user_id: "ana", name: "Ana" }] }, t)).toBe("Only you, for now");
  });
});
