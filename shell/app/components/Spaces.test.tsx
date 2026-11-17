import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { type Space, looksLikeCode, memberLabel, membersLine, myName } from "../lib/spaces";
import { SpacesView } from "./Spaces";

const ANA = "0a0a0a0a-0000-4000-8000-00000000000a";
const LUIS = "0b0b0b0b-0000-4000-8000-00000000000b";
const EVA = "0e0e0e0e-0000-4000-8000-00000000000e";

const home: Space = {
  id: "0c0c0c0c-0000-4000-8000-00000000c0c0",
  name: "Home",
  role: "owner",
  me: ANA,
  members: [
    { user_id: ANA, role: "owner", name: "Ana" },
    { user_id: LUIS, role: "member", name: "Luis" },
    { user_id: EVA, role: "member", name: null },
  ],
};

describe("who is in a space", () => {
  it("you are You even with a name, and whoever set none shows as unnamed", () => {
    expect(home.members.map((member) => memberLabel(home, member))).toEqual(["You", "Luis", "No name"]);
  });

  it("it reads as one line, you first", () => {
    expect(membersLine(home)).toBe("You, Luis and No name");
    expect(membersLine({ ...home, members: home.members.slice(0, 2) })).toBe("You and Luis");
    expect(membersLine({ ...home, members: home.members.slice(0, 1) })).toBe("Only you, for now");
  });

  it("your name is the one you set in that space", () => {
    expect(myName(home)).toBe("Ana");
    expect(myName({ ...home, me: EVA })).toBe("");
  });
});

describe("a code", () => {
  it("works with dashes, spaces or lowercase, and not with fewer than twelve", () => {
    expect(looksLikeCode("abcd efgh jkmn")).toBe(true);
    expect(looksLikeCode("ABCD-EFGH-JKMN")).toBe(true);
    expect(looksLikeCode("ABCD-EFGH")).toBe(false);
  });
});

describe("spaces in Settings", () => {
  it("lists each space with who is in it, and lets you create one or join with a code", () => {
    const html = renderToStaticMarkup(<SpacesView spaces={[home]} />);

    expect(html).toContain("Spaces");
    expect(html).toContain("Home");
    expect(html).toContain("You, Luis and No name");
    expect(html).toContain("New space");
    expect(html).toContain("I have a code");
  });

  it("without spaces, it says what one is and how to join", () => {
    const html = renderToStaticMarkup(<SpacesView spaces={[]} />);

    expect(html).toContain("nobody can find you");
    expect(html).not.toContain('class="list"');
  });

  it("if the kernel does not answer, it says so instead of showing you have none", () => {
    const html = renderToStaticMarkup(<SpacesView spaces={null} failed onRetry={() => {}} />);

    expect(html).toContain("Your spaces could not be loaded");
    expect(html).toContain("Try again");
  });
});
