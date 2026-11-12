import { renderToString } from "react-dom/server";

import type { Reading } from "./api";
import { ReadingFields } from "./ReadingFields";

const GENRES = [
  { id: "novel", name: "Novela" },
  { id: "other", name: "Otros" },
];

function render(reading: Partial<Reading>): string {
  const full: Reading = {
    status: "want",
    started_on: null,
    finished_on: null,
    rating: null,
    format: "paper",
    genre: "other",
    note: null,
    ...reading,
  };
  return renderToString(<ReadingFields reading={full} genres={GENRES} onChange={() => {}} />);
}

describe("los campos de la lectura", () => {
  it("un libro que quieres leer no pide fechas ni valoración", () => {
    const html = render({ status: "want" });

    expect(html).not.toContain("Empezado");
    expect(html).not.toContain("Sin valorar");
    expect(html).toContain("Novela");
  });

  it("uno leído pide inicio, fin y valoración", () => {
    const html = render({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20", rating: 4.5 });

    expect(html).toContain("Empezado");
    expect(html).toContain("Terminado");
    expect(html).toContain("Quitar valoración");
  });

  it("la valoración se ve con su nombre y su nota, no solo la barra", () => {
    expect(render({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20", rating: null })).toMatch(
      /library-rating-head.*Valoración.*Sin valorar/,
    );
    expect(render({ status: "reading", started_on: "2026-09-01", rating: 4.5 })).toMatch(
      /library-rating-head.*Valoración.*4,5/,
    );
  });

  it("uno abandonado dice cuándo lo dejaste", () => {
    expect(render({ status: "abandoned", started_on: "2026-09-01" })).toContain("Dejado");
  });
});
