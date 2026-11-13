import { renderToString } from "react-dom/server";

import type { Reading } from "./api";
import { ReadingFields } from "./ReadingFields";

const GENRES = [
  { id: "novel", name: "Novel" },
  { id: "other", name: "Other" },
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

describe("the reading fields", () => {
  it("a book you want to read asks for no dates or rating", () => {
    const html = render({ status: "want" });

    expect(html).not.toContain("Started");
    expect(html).not.toContain("Not rated");
    expect(html).toContain("Novel");
  });

  it("a read one asks for start, end and rating", () => {
    const html = render({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20", rating: 4.5 });

    expect(html).toContain("Started");
    expect(html).toContain("Finished");
    expect(html).toContain("Remove rating");
  });

  it("the rating shows its name and value, not just the slider", () => {
    expect(render({ status: "read", started_on: "2026-09-01", finished_on: "2026-09-20", rating: null })).toMatch(
      /library-rating-head.*Rating.*Not rated/,
    );
    expect(render({ status: "reading", started_on: "2026-09-01", rating: 4.5 })).toMatch(
      /library-rating-head.*Rating.*4\.5/,
    );
  });

  it("an abandoned one says when you left it", () => {
    expect(render({ status: "abandoned", started_on: "2026-09-01" })).toContain("Abandoned");
  });
});
