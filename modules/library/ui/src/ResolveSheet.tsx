import { Button, Hint, List, ListRow, Sheet, Skeleton, TextField } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { type Book, type Search, asCandidate, resolveBook, searchCatalog } from "./api";
import { candidateDetail, failedNote } from "./words";

export function ResolveSheet({
  book,
  onClose,
  onResolved,
  onError,
}: {
  book: Book;
  onClose: () => void;
  onResolved: (book: Book) => void;
  onError: (error: unknown) => void;
}) {
  const [query, setQuery] = useState(book.isbn13 ?? [book.title, book.authors[0]].filter(Boolean).join(" "));
  const [found, setFound] = useState<Search | null>(null);
  const [searching, setSearching] = useState(false);

  const search = useCallback(
    async (text: string) => {
      if (text.trim().length < 2) return;
      setSearching(true);
      try {
        setFound(await searchCatalog(text.trim()));
      } catch (error) {
        onError(error);
      } finally {
        setSearching(false);
      }
    },
    [onError],
  );

  useEffect(() => {
    void search(query);
  }, []);

  return (
    <Sheet title="Buscar su edición" onClose={onClose}>
      <div className="library-fields">
        <TextField label="Buscar" type="search" value={query} onChange={setQuery} onSubmit={() => void search(query)} />
        <Button variant="tinted" onClick={() => void search(query)}>
          Buscar
        </Button>
        {searching && <Skeleton rows={3} label="Buscando" />}
        {found && failedNote(found.failed) && <Hint tone="warning">{failedNote(found.failed)}</Hint>}
        {found && !searching && found.candidates.length === 0 && <Hint>No sale en ningún catálogo.</Hint>}
        {found && found.candidates.length > 0 && (
          <List>
            {found.candidates.map((candidate) => (
              <ListRow
                key={`${candidate.source}:${candidate.source_ref}`}
                title={candidate.title}
                subtitle={candidate.authors.join(", ") || undefined}
                detail={candidateDetail(candidate)}
                accessory="done"
                onClick={() => void resolveBook(book.id, asCandidate(candidate)).then(onResolved).catch(onError)}
              />
            ))}
          </List>
        )}
      </div>
    </Sheet>
  );
}
