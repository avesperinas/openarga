import { ACTIONS, EQUIPMENT, USUALLY_UNATTENDED, whenLabel } from "./steps";

test("cada verbo del esquema tiene su palabra en español", () => {
  const schema = [
    "wash", "peel", "chop", "mix", "knead", "season", "coat",
    "fry", "saute", "boil", "simmer", "steam", "bake", "roast", "grill", "toast",
    "rest", "marinate", "chill", "freeze", "prove", "blend", "strain",
    "assemble", "serve",
  ];

  expect(Object.keys(ACTIONS).sort()).toEqual(schema.sort());
});

test("y cada aparato también", () => {
  expect(Object.keys(EQUIPMENT).sort()).toEqual(
    ["air_fryer", "board", "bowl", "fridge", "hob", "none", "oven"].sort(),
  );
});

test("lo que suele correr solo se propone como tal, y todo eso es un verbo conocido", () => {
  for (const action of USUALLY_UNATTENDED) expect(ACTIONS[action]).toBeDefined();
  expect(USUALLY_UNATTENDED.has("bake")).toBe(true);
  expect(USUALLY_UNATTENDED.has("chop")).toBe(false);
});

test("el momento de un paso se lee en minutos desde que te pones", () => {
  expect(whenLabel(0, 5)).toBe("min 0 a 5");
  expect(whenLabel(20, 20)).toBe("min 20");
});
