import { invalidate, mutate, peek, prime, useResource } from "@openarga/app";
import {
  Card,
  ChoiceChips,
  CoverWall,
  CreateButton,
  EmptyState,
  ErrorState,
  GroupLabel,
  Hint,
  MediaCard,
  OfflineNotice,
  RingFigure,
  Screen,
  SelectField,
  Skeleton,
  todayIso,
} from "@openarga/ui";
import { useCallback, useMemo, useState } from "react";

import { AddSheet } from "./AddSheet";
import { AppVersion } from "./AppVersion";
import { type Book, type Genre, type YearStats, Unauthorised, coverUrl, readBooks, readStats, saveReading, signIn } from "./api";
import { Cover } from "./Cover";
import { ScreenHeader } from "./Header";
import { t } from "./lang";
import { type Filters, NO_FILTERS, datesLine, filtered, formats, goalPace, shelves, stars, withStatus } from "./words";

export function LibraryScreen({ genres, onOpen }: { genres: Genre[]; onOpen: (book: Book) => void }) {
  const shelf = useResource("books", readBooks, { persist: true });
  const books = shelf.data ?? null;
  const [problem, setProblem] = useState("");
  const [adding, setAdding] = useState(false);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : t("problem.save"));
  }, []);

  const all = books ?? [];
  const reading = all.filter((book) => book.status === "reading");
  const walls = useMemo(
    () => shelves(filtered(all, filters)).filter((shelf) => shelf.id !== "reading"),
    [all, filters],
  );
  const filtering = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS);
  const thisYear = Number(todayIso().slice(0, 4));
  const year = useResource<YearStats>(`stats:${thisYear}`, () => readStats());
  const goal = year.data?.goal ? year.data : null;
  const present = genres.filter((one) => all.some((book) => book.genre === one.id));
  const [finishing, setFinishing] = useState<string | null>(null);

  async function finish(book: Book) {
    setProblem("");
    setFinishing(book.id);
    const shown = { ...book, ...withStatus(book, "read", todayIso()) };
    const request = saveReading(book.id, withStatus(book, "read", todayIso()));
    const replace = (list: Book[] | undefined, one: Book) => (list ?? []).map((other) => (other.id === one.id ? one : other));
    void mutate<Book>(`book:${book.id}`, shown, { request: () => request }).catch(() => undefined);
    try {
      await mutate<Book[]>("books", (now) => replace(now, shown), {
        request: () => request.then((fresh) => replace(peek<Book[]>("books"), fresh)),
      });
      invalidate("stats:");
    } catch (error) {
      fail(error);
    } finally {
      setFinishing(null);
    }
  }

  return (
    <Screen>
      <ScreenHeader title={t("shelf.title")} />
      <OfflineNotice />

      <CreateButton label={t("shelf.add_short")} onClick={() => setAdding(true)} />

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {shelf.error && books === null && (
        <ErrorState title={t("shelf.error")} detail={shelf.error.message} onRetry={shelf.refresh} />
      )}

      {shelf.loading && <Skeleton rows={4} />}

      {books !== null && books.length === 0 && (
        <EmptyState
          icon="book"
          hue={5}
          title={t("shelf.empty")}
          action={{ label: t("shelf.add"), icon: "plus", onClick: () => setAdding(true) }}
        >
          {t("shelf.empty_body")}
        </EmptyState>
      )}

      {goal && (
        <Card>
          <RingFigure
            size="medium"
            share={goal.books / goal.goal!}
            value={goal.books}
            label={t("goal.this_year", { books: goal.books, goal: goal.goal! })}
            detail={goalPace(goal) || undefined}
            tone={goal.goal_pace !== null && goal.books + 0.5 < goal.goal_pace ? "warning" : undefined}
          />
        </Card>
      )}

      {reading.length > 0 && (
        <section className="library-group" aria-label={t("shelf.reading")}>
          <GroupLabel>{t("shelf.reading")}</GroupLabel>
          {reading.map((book) => (
            <MediaCard
              key={book.id}
              media={<Cover book={book} size="large" />}
              title={book.title}
              lines={[
                ...(book.authors.length > 0 ? [book.authors.join(", ")] : []),
                datesLine(book),
                ...(book.pages ? [t("edition.pages", { pages: book.pages })] : []),
              ]}
              onOpen={() => onOpen(book)}
              action={{ label: t("action.finished_today"), icon: "done", disabled: finishing === book.id, onClick: () => void finish(book) }}
            />
          ))}
        </section>
      )}

      {books !== null && books.some((book) => book.status !== "reading") && (
        <>
          {present.length > 1 && (
            <ChoiceChips
              label={t("field.genre")}
              value={filters.genre}
              onChange={(genre) => setFilters({ ...filters, genre })}
              options={[{ value: "all", label: t("filter.all_genres") }, ...present.map((one) => ({ value: one.id, label: one.name }))]}
            />
          )}
          <div className="library-filters">
            <SelectField
              label={t("field.format")}
              options={[{ value: "all", label: t("filter.all_formats") }, ...formats()]}
              value={filters.format}
              onChange={(format) => setFilters({ ...filters, format })}
            />
            <SelectField
              label={t("field.rating")}
              options={[
                { value: "all", label: t("filter.all_ratings") },
                { value: "3", label: t("filter.or_more", { stars: stars(3) }) },
                { value: "4", label: t("filter.or_more", { stars: stars(4) }) },
                { value: "5", label: stars(5) },
              ]}
              value={filters.rating}
              onChange={(rating) => setFilters({ ...filters, rating })}
            />
          </div>
        </>
      )}
      {filtering && walls.length === 0 && <Hint>{t("filter.none")}</Hint>}

      {walls.map((shelf) => (
        <section key={shelf.id} className="library-group" aria-label={shelf.title}>
          <GroupLabel>
            {shelf.title} <span className="library-count">{shelf.books.length}</span>
          </GroupLabel>
          <CoverWall
            label={shelf.title}
            onOpen={(id) => {
              const book = shelf.books.find((one) => one.id === id);
              if (book) onOpen(book);
            }}
            items={shelf.books.map((book) => ({
              id: book.id,
              title: book.title,
              subtitle: book.authors[0],
              src: book.has_cover ? coverUrl(book) : null,
              note: book.rating !== null ? stars(book.rating) : undefined,
              muted: book.status === "abandoned" || book.status === "want",
            }))}
          />
        </section>
      ))}
      <AppVersion />

      {adding && (
        <AddSheet
          genres={genres}
          onClose={() => setAdding(false)}
          onAdded={(book) => {
            setAdding(false);
            setProblem("");
            void mutate<Book[]>("books", (all) => [book, ...(all ?? [])]);
            prime(`book:${book.id}`, book);
            invalidate("stats:");
            onOpen(book);
          }}
          onError={fail}
        />
      )}
    </Screen>
  );
}
