import { ACTIONS, EQUIPMENT, USUALLY_UNATTENDED, actionName, equipmentName, whenLabel } from "./steps";
import { english as t, spanish } from "./i18n/testing";

test("every verb in the schema has its word in both languages", () => {
  const schema = [
    "wash", "peel", "chop", "mix", "knead", "season", "coat",
    "fry", "saute", "boil", "simmer", "steam", "bake", "roast", "grill", "toast",
    "rest", "marinate", "chill", "freeze", "prove", "blend", "strain",
    "assemble", "serve",
  ];

  expect([...ACTIONS].sort()).toEqual(schema.sort());
  for (const action of ACTIONS) {
    expect(actionName(t, action)).not.toBe(`action.${action}`);
    expect(actionName(spanish, action)).not.toBe(`action.${action}`);
  }
});

test("and so does every appliance", () => {
  expect([...EQUIPMENT].sort()).toEqual(["air_fryer", "board", "bowl", "fridge", "hob", "none", "oven"].sort());
  expect(equipmentName(t, "air_fryer")).toBe("Air fryer");
});

test("what usually runs by itself is offered as such, and all of it is a known verb", () => {
  for (const action of USUALLY_UNATTENDED) expect(ACTIONS).toContain(action);
  expect(USUALLY_UNATTENDED.has("bake")).toBe(true);
  expect(USUALLY_UNATTENDED.has("chop")).toBe(false);
});

test("a step's moment reads in minutes from when you start", () => {
  expect(whenLabel(0, 5, t)).toBe("min 0 to 5");
  expect(whenLabel(20, 20, t)).toBe("min 20");
});
