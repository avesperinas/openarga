import { invalidate, mutate, peek, useResource } from "@openarga/app";
import { Badge, Button, Card, ErrorState, Figures, Hint, Inline, MediaHero, OfflineNotice, Screen, Skeleton } from "@openarga/ui";
import { useCallback, useState } from "react";

import { type Book, type Genre, Unauthorised, readBook, saveReading, signIn } from "./api";
import { BookSheet } from "./BookSheet";
import { Cover } from "./Cover";
import { ScreenHeader } from "./Header";
import { ResolveSheet } from "./ResolveSheet";
import { t } from "./lang";
import { datesLine, editionLine, formats, stars, statusName, todayIso, withStatus } from "./words";

export function BookScreen({ id, genres, onBack }: { id: string; genres: Genre[]; onBack: () => void }) {
  const found = useResource(`book:${id}`, () => readBook(id), {
    initial: () => peek<Book[]>("books")?.find((one) => one.id === id),
  });
  const book = found.data ?? null;
  const [problem, setProblem] = useState("");
  const [editing, setEditing] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [moving, setMoving] = useState(false);

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : t("problem.save"));
  }, []);

  const saved = useCallback((fresh: Book) => {
    void mutate(`book:${fresh.id}`, fresh);
    void mutate<Book[]>("books", (all) => (all ?? []).map((one) => (one.id === fresh.id ? fresh : one)));
    invalidate("stats:");
  }, []);

  async function move(status: "reading" | "read") {
    if (!book) return;
    setProblem("");
    setMoving(true);
    const next = withStatus(book, status, todayIso());
    try {
      await mutate<Book>(`book:${book.id}`, { ...book, ...next }, { request: () => saveReading(book.id, next) });
      const fresh = peek<Book>(`book:${book.id}`);
      if (fresh) saved(fresh);
    } catch (error) {
      fail(error);
    } finally {
      setMoving(false);
    }
  }

  const back = { label: t("shelf.title"), onClick: onBack };
  if (!book) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <OfflineNotice />
        {found.error ? (
          <ErrorState title={t("book.error")} detail={found.error.message} onRetry={found.refresh} />
        ) : (
          <Skeleton rows={5} />
        )}
      </Screen>
    );
  }

  const genre = genres.find((one) => one.id === book.genre)?.name ?? book.genre;
  const format = formats().find((one) => one.value === book.format)?.label ?? book.format;

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={statusName(book.status)} title={book.title} />
      <OfflineNotice />

      <MediaHero media={<Cover book={book} size="hero" />}>
        {book.subtitle && <Hint>{book.subtitle}</Hint>}
        {book.authors.length > 0 && <p className="library-book-authors">{book.authors.join(", ")}</p>}
        <Hint>{editionLine(book)}</Hint>
        {book.rating !== null && <p className="library-reading-rating">{stars(book.rating)}</p>}
      </MediaHero>
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {(book.pages || book.days) && (
        <Card>
          <Figures
            label={t("book.reading")}
            items={[
              ...(book.pages ? [{ label: t("book.pages"), value: book.pages }] : []),
              ...(book.days ? [{ label: book.days === 1 ? t("book.day") : t("book.days"), value: book.days }] : []),
              ...(book.pages && book.days ? [{ label: t("book.pages_per_day"), value: Math.round(book.pages / book.days), lit: true }] : []),
            ]}
          />
          <Hint>{datesLine(book)}</Hint>
        </Card>
      )}
      {!(book.pages || book.days) && <Hint>{datesLine(book)}</Hint>}
      {book.note && (
        <Card title={t("book.note")}>
          <Hint lines>{book.note}</Hint>
        </Card>
      )}
      <Inline label={t("book.genre_and_format")}>
        <Badge>{genre}</Badge>
        <Badge>{format}</Badge>
        {book.language && <Badge>{book.language}</Badge>}
      </Inline>
      <div className="library-actions">
        {book.status === "want" && (
          <Button variant="tinted" disabled={moving} onClick={() => void move("reading")}>
            {t("action.start_today")}
          </Button>
        )}
        {book.status === "reading" && (
          <Button variant="tinted" disabled={moving} onClick={() => void move("read")}>
            {t("action.finished_today")}
          </Button>
        )}
        <Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>
          {t("action.edit")}
        </Button>
      </div>

      {book.edition === "manual" && (
        <section className="library-group">
          <Hint>
            {book.source === "tool"
              ? t("book.manual_ai")
              : t("book.manual_typed")}
          </Hint>
          <Button variant="plain" onClick={() => setResolving(true)}>
            {t("book.find_edition")}
          </Button>
        </section>
      )}

      {editing && (
        <BookSheet
          book={book}
          genres={genres}
          onClose={() => setEditing(false)}
          onSaved={(fresh) => {
            setEditing(false);
            setProblem("");
            saved(fresh);
          }}
          onError={fail}
        />
      )}
      {resolving && (
        <ResolveSheet
          book={book}
          onClose={() => setResolving(false)}
          onResolved={(fresh) => {
            setResolving(false);
            saved(fresh);
          }}
          onError={fail}
        />
      )}
    </Screen>
  );
}
