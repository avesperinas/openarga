# Books (Library)

The books you read and want to read. Library keeps one row per **reading**: read a book twice and
it is two readings, each with its dates, rating, format, genre and note, on top of the book's
**edition** (title, authors, pages, language, year, ISBN, cover).

Module id `library`, schema `library`, role `mod_library`. Code in
[`modules/library`](../../modules/library), manifest in
[`manifest.yaml`](../../modules/library/manifest.yaml), glossary in
[`tools/glossary.md`](../../modules/library/tools/glossary.md).

## Screens

| Route | What it shows |
|---|---|
| `/library/` | The shelf: what you are reading, this year's goal, what you read by year, what you want to read, and filters by genre, format and rating |
| `/library/books/<id>` | One reading: its edition, dates, pages per day, note, and buttons to start or finish it today |
| `/library/stats` | A year in figures: books, pages, pages per day, goal and pace, pages per month and per day, genres, authors, ratings, formats, languages, the longest and the quickest, and the change against the year before |
| `/library/settings` | The app's settings |

The UI is in English and Spanish (`ui/src/i18n/{en,es}.json`) and follows the person's locale and
time zone. Server texts (genre and language names, widgets, panel, Notes records) come from
`src/library/i18n/{en,es}.json`.

## Adding a book

- **Search** by title, author or ISBN, or **scan** the barcode. Candidates come from the book
  catalogs through the hub (`books.search`; Open Library and Google Books) and the cover through
  `books.cover`. Choosing one stores its edition, which cannot be edited: it belongs to its source.
- **Type it in** when no catalog has it. A typed book can be resolved later to a catalog edition
  ("Find its edition").
- The genre is proposed from the catalog's subjects (`genre.py`) and can be changed: novel, essay,
  history, science, biography, business, fantasy and science fiction, crime, poetry, comics, other.

The status carries its dates: *want* has none, *reading* has a start, *read* has a start and an
end, *abandoned* has at least a start. Dates cannot be after today, in the person's time zone.
Ratings go from 0 to 5 in half points.

## Pages per day

Library does not track page-by-page progress. Each book's pages are spread evenly between its start
and its end. That estimate feeds the pages-per-day figure, the calendar of pages, and the `pages`
metric.

## Tools

Read (`library:read`): `find_books`, `get_currently_reading`, `get_reading_stats`.
Write (`library:write`): `add_book`, `start_reading`, `finish_reading`, `rate_book`. Their
descriptions are in the [manifest](../../modules/library/manifest.yaml). `add_book` with an ISBN
resolves the edition from the catalog. Without one, it saves the title and authors unresolved, to
be resolved in the app.

## What it shares with other apps

- **`books.want`**: another app (Insights, for instance) can ask Library through the kernel to add
  a book to "want to read". The same book twice is not repeated.
- **Notes**: every reading is a record, and the days you started or finished a book are a diary
  entry.
- **Insights**: the metrics `library.books_finished` and `library.pages`, per day.
- **Home**: widgets for what you are reading, the year's goal and pages per month, and a panel
  that says whether you are on pace.

## Demo

[`src/library/demo.py`](../../modules/library/src/library/demo.py) seeds Alex and Sam from
[`demo/personas.yaml`](../../demo/personas.yaml): about two books a month over eighteen months, one
abandoned, one in progress, three wanted, and goals for this year and the last. Titles and authors
are invented. It can run any number of times.
