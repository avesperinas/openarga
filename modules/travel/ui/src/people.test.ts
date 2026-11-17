import { describe, expect, it } from "vitest";

import { travellerLabel } from "./people";

const members = new Map([["ana-id", "Ana"], ["luis-id", "Luis"]]);
const one = (name: string, me: boolean, member: string | null = null) => ({
  id: name,
  name,
  me,
  position: 0,
  member_user_id: member,
});

describe("what each traveller is called", () => {
  it("whoever looks is “You”, even if the trip calls them otherwise", () => {
    expect(travellerLabel(one("Luis", true, "luis-id"), members)).toBe("You");
  });

  it("“Me” for the others is whoever created the trip, with their name in the space", () => {
    expect(travellerLabel(one("Yo", false, "ana-id"), members)).toBe("Ana");
    expect(travellerLabel(one("Yo", false, "otra-id"), members)).toBe("Whoever created the trip");
  });

  it("the others, with the name they have in the trip", () => {
    expect(travellerLabel(one("Viajero 3", false), members)).toBe("Viajero 3");
  });
});
