import { invalidate, mutate, peek, useResource } from "@openarga/app";
import { Badge, Button, Card, ErrorState, Figures, Hint, Inline, MediaHero, OfflineNotice, Screen, Skeleton } from "@openarga/ui";
import { useCallback, useState } from "react";

import { type Book, type Genre, Unauthorised, readBook, saveReading, signIn } from "./api";
import { BookSheet } from "./BookSheet";
import { Cover } from "./Cover";
import { ScreenHeader } from "./Header";
import { ResolveSheet } from "./ResolveSheet";
import { FORMATS, STATUS_NAMES, datesLine, editionLine, stars, todayIso, withStatus } from "./words";

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
    setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
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

  const back = { label: "Tus libros", onClick: onBack };
  if (!book) {
    return (
      <Screen>
        <ScreenHeader back={back} />
        <OfflineNotice />
        {found.error ? (
          <ErrorState title="No se ha podido abrir el libro" detail={found.error.message} onRetry={found.refresh} />
        ) : (
          <Skeleton rows={5} />
        )}
      </Screen>
    );
  }

  const genre = genres.find((one) => one.id === book.genre)?.name ?? book.genre;
  const format = FORMATS.find((one) => one.value === book.format)?.label ?? book.format;

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={STATUS_NAMES[book.status]} title={book.title} />
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
            label="Su lectura"
            items={[
              ...(book.pages ? [{ label: "páginas", value: book.pages }] : []),
              ...(book.days ? [{ label: book.days === 1 ? "día" : "días", value: book.days }] : []),
              ...(book.pages && book.days ? [{ label: "páginas al día", value: Math.round(book.pages / book.days), lit: true }] : []),
            ]}
          />
          <Hint>{datesLine(book)}</Hint>
        </Card>
      )}
      {!(book.pages || book.days) && <Hint>{datesLine(book)}</Hint>}
      {book.note && (
        <Card title="Tu nota">
          <Hint lines>{book.note}</Hint>
        </Card>
      )}
      <Inline label="Temática y formato">
        <Badge>{genre}</Badge>
        <Badge>{format}</Badge>
        {book.language && <Badge>{book.language}</Badge>}
      </Inline>
      <div className="library-actions">
        {book.status === "want" && (
          <Button variant="tinted" disabled={moving} onClick={() => void move("reading")}>
            Empezarlo hoy
          </Button>
        )}
        {book.status === "reading" && (
          <Button variant="tinted" disabled={moving} onClick={() => void move("read")}>
            Terminado hoy
          </Button>
        )}
        <Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>
          Editar
        </Button>
      </div>

      {book.edition === "manual" && (
        <section className="library-group">
          <Hint>
            {book.source === "tool"
              ? "Lo apuntó Claude sin su edición. Búscala para tener la portada y los datos del catálogo."
              : "Está tecleado. Si está en algún catálogo, búscalo para tener su portada."}
          </Hint>
          <Button variant="plain" onClick={() => setResolving(true)}>
            Buscar su edición
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
