import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { type Space, looksLikeCode, memberLabel, membersLine, myName } from "../lib/spaces";
import { SpacesView } from "./Spaces";

const ANA = "0a0a0a0a-0000-4000-8000-00000000000a";
const LUIS = "0b0b0b0b-0000-4000-8000-00000000000b";
const EVA = "0e0e0e0e-0000-4000-8000-00000000000e";

const casa: Space = {
  id: "0c0c0c0c-0000-4000-8000-00000000c0c0",
  name: "Casa",
  role: "owner",
  me: ANA,
  members: [
    { user_id: ANA, role: "owner", name: "Ana" },
    { user_id: LUIS, role: "member", name: "Luis" },
    { user_id: EVA, role: "member", name: null },
  ],
};

describe("quién está en un espacio", () => {
  it("tú eres Tú aunque tengas nombre, y quien no lo puso sale sin nombre", () => {
    expect(casa.members.map((member) => memberLabel(casa, member))).toEqual(["Tú", "Luis", "Sin nombre"]);
  });

  it("se dice en una línea, contigo primero", () => {
    expect(membersLine(casa)).toBe("Tú, Luis y Sin nombre");
    expect(membersLine({ ...casa, members: casa.members.slice(0, 2) })).toBe("Tú y Luis");
    expect(membersLine({ ...casa, members: casa.members.slice(0, 1) })).toBe("Solo tú, de momento");
  });

  it("tu nombre es el que pusiste en ese espacio", () => {
    expect(myName(casa)).toBe("Ana");
    expect(myName({ ...casa, me: EVA })).toBe("");
  });
});

describe("un código", () => {
  it("vale con guiones, espacios o minúsculas, y no con menos de doce", () => {
    expect(looksLikeCode("abcd efgh jkmn")).toBe(true);
    expect(looksLikeCode("ABCD-EFGH-JKMN")).toBe(true);
    expect(looksLikeCode("ABCD-EFGH")).toBe(false);
  });
});

describe("los espacios en Ajustes", () => {
  it("lista cada espacio con quién está, y deja crear uno o entrar con un código", () => {
    const html = renderToStaticMarkup(<SpacesView spaces={[casa]} />);

    expect(html).toContain("Espacios");
    expect(html).toContain("Casa");
    expect(html).toContain("Tú, Luis y Sin nombre");
    expect(html).toContain("Nuevo espacio");
    expect(html).toContain("Tengo un código");
  });

  it("sin espacios, dice qué es uno y cómo se entra", () => {
    const html = renderToStaticMarkup(<SpacesView spaces={[]} />);

    expect(html).toContain("nadie puede encontrarte");
    expect(html).not.toContain('class="list"');
  });

  it("si el kernel no contesta, lo dice en vez de enseñar que no tienes ninguno", () => {
    const html = renderToStaticMarkup(<SpacesView spaces={null} failed onRetry={() => {}} />);

    expect(html).toContain("No se han podido traer tus espacios");
    expect(html).toContain("Reintentar");
  });
});
