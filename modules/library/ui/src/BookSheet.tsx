import { Hint, Sheet } from "@openarga/ui";
import { useState } from "react";

import { type Book, type Edition, type Genre, type Reading, saveEdition, saveReading } from "./api";
import { EditionFields } from "./EditionFields";
import { ReadingFields } from "./ReadingFields";
import { authorsOf } from "./words";
import { t } from "./lang";

function readingOf(book: Book): Reading {
  const { status, started_on, finished_on, rating, format, genre, note } = book;
  return { status, started_on, finished_on, rating, format, genre, note };
}

function editionOf(book: Book): Edition {
  const { title, subtitle, authors, pages, language, year, isbn13 } = book;
  return { title, subtitle, authors, pages, language, year, isbn: isbn13 };
}

export function BookSheet({
  book,
  genres,
  onClose,
  onSaved,
  onError,
}: {
  book: Book;
  genres: Genre[];
  onClose: () => void;
  onSaved: (book: Book) => void;
  onError: (error: unknown) => void;
}) {
  const [edition, setEdition] = useState(() => editionOf(book));
  const [reading, setReading] = useState(() => readingOf(book));
  const [saving, setSaving] = useState(false);
  const typed = book.edition === "manual";

  async function save() {
    setSaving(true);
    try {
      if (typed) await saveEdition(book.id, edition);
      onSaved(await saveReading(book.id, reading));
    } catch (error) {
      onError(error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet
      title={book.title}
      onClose={onClose}
      action={{ label: t("action.save"), onClick: () => void save(), disabled: saving || !edition.title.trim() }}
    >
      {typed ? (
        <EditionFields edition={edition} onChange={setEdition} />
      ) : (
        <Hint>
          {[authorsOf(book), book.pages ? t("edition.pages", { pages: book.pages }) : "", book.year?.toString() ?? ""]
            .filter(Boolean)
            .join(" · ")}
        </Hint>
      )}
      {book.days !== null && (
        <Hint>
          {book.days === 1 ? t("book.read_in_one") : t("book.read_in", { days: book.days })}
        </Hint>
      )}
      <ReadingFields reading={reading} genres={genres} onChange={setReading} />
    </Sheet>
  );
}
