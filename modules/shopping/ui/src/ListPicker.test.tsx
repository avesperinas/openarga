import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Space } from "./api";
import { english, inLocale, spanish } from "./i18n/testing";
import { ListPicker, listSubtitle, listTitle, withWhom } from "./ListPicker";

const ALEX = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const SAM = "0b0b0b0b-0000-4000-8000-00000000b0b0";
const home: Space = {
  id: "0c0c0c0c-0000-4000-8000-00000000c0c0",
  name: "Home",
  me: ALEX,
  members: [
    { user_id: ALEX, name: "Alex" },
    { user_id: SAM, name: "Sam" },
  ],
};

describe("whose list it is", () => {
  it("yours is called so and only you see it", () => {
    expect(listTitle(english, { space_id: null }, [home])).toBe("Your list");
    expect(listSubtitle(english, { space_id: null }, [home])).toBe("Only you see it");
  });

  it("a space's list carries its name and says who sees it", () => {
    expect(listTitle(english, { space_id: home.id }, [home])).toBe("Home");
    expect(listSubtitle(english, { space_id: home.id }, [home])).toBe("They see and tick it: You and Sam");
  });

  it("whoever has no name shows as such, and with nobody else it is only you", () => {
    const eve = { user_id: "0e0e0e0e-0000-4000-8000-00000000e0e0", name: null };
    expect(withWhom(english, { ...home, members: [...home.members, eve] })).toBe("You, Sam and No name");
    expect(withWhom(english, { ...home, members: home.members.slice(0, 1) })).toBe("Only you, for now");
    expect(withWhom(spanish, { ...home, members: home.members.slice(0, 1) })).toBe(spanish("picker.whom_alone"));
  });

  it("it shows on screen with its name, closed until it is tapped", () => {
    const html = renderToStaticMarkup(
      inLocale(<ListPicker list={{ space_id: home.id }} spaces={[home]} onChoose={async () => {}} />),
    );

    expect(html).toContain("Home");
    expect(html).toContain("You and Sam");
    expect(html).not.toContain(english("picker.title"));
  });
});
