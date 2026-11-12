import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Space } from "./api";
import { ListPicker, listSubtitle, listTitle, withWhom } from "./ListPicker";

const ANA = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const LUIS = "0b0b0b0b-0000-4000-8000-00000000b0b0";
const casa: Space = {
  id: "0c0c0c0c-0000-4000-8000-00000000c0c0",
  name: "Casa",
  me: ANA,
  members: [
    { user_id: ANA, name: "Ana" },
    { user_id: LUIS, name: "Luis" },
  ],
};

describe("de quién es la lista", () => {
  it("la tuya se llama así y solo la ves tú", () => {
    expect(listTitle({ space_id: null }, [casa])).toBe("Tu lista");
    expect(listSubtitle({ space_id: null }, [casa])).toBe("Solo la ves tú");
  });

  it("la de un espacio lleva su nombre y dice quién la ve", () => {
    expect(listTitle({ space_id: casa.id }, [casa])).toBe("Casa");
    expect(listSubtitle({ space_id: casa.id }, [casa])).toBe("La ven y la marcan: Tú y Luis");
  });

  it("quien no puso nombre sale sin nombre, y sin nadie más eres solo tú", () => {
    const eva = { user_id: "0e0e0e0e-0000-4000-8000-00000000e0e0", name: null };
    expect(withWhom({ ...casa, members: [...casa.members, eva] })).toBe("Tú, Luis y Sin nombre");
    expect(withWhom({ ...casa, members: casa.members.slice(0, 1) })).toBe("Solo tú, de momento");
  });

  it("se ve en la pantalla con su nombre, cerrada hasta que se toca", () => {
    const html = renderToStaticMarkup(
      <ListPicker list={{ space_id: casa.id }} spaces={[casa]} onChoose={async () => {}} />,
    );

    expect(html).toContain("Casa");
    expect(html).toContain("Tú y Luis");
    expect(html).not.toContain("Qué lista usas");
  });
});
