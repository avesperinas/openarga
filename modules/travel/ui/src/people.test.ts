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

describe("cómo se llama a cada viajero", () => {
  it("quien mira es «Tú», aunque el viaje le llame de otra forma", () => {
    expect(travellerLabel(one("Luis", true, "luis-id"), members)).toBe("Tú");
  });

  it("«Yo» para los demás es quien creó el viaje, con su nombre del espacio", () => {
    expect(travellerLabel(one("Yo", false, "ana-id"), members)).toBe("Ana");
    expect(travellerLabel(one("Yo", false, "otra-id"), members)).toBe("Quien creó el viaje");
  });

  it("los demás, con el nombre que tienen en el viaje", () => {
    expect(travellerLabel(one("Viajero 3", false), members)).toBe("Viajero 3");
  });
});
