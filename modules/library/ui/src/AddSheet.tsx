import { Button, Hint, List, ListRow, Sheet, Skeleton, TextField } from "@openarga/ui";
import { useCallback, useState } from "react";

import {
  type Book,
  type Edition,
  type FoundCandidate,
  type Genre,
  type Reading,
  type Search,
  addBook,
  addFromCatalog,
  asCandidate,
  searchCatalog,
} from "./api";
import { EditionFields } from "./EditionFields";
import { ReadingFields } from "./ReadingFields";
import { Scanner } from "./Scanner";
import { candidateDetail, failedNote } from "./words";

const EMPTY_EDITION: Edition = { title: "", authors: [] };
export const EMPTY_READING: Reading = {
  status: "want",
  started_on: null,
  finished_on: null,
  rating: null,
  format: "paper",
  genre: "other",
  note: null,
};

type Step =
  | { kind: "search" }
  | { kind: "scan" }
  | { kind: "chosen"; candidate: FoundCandidate }
  | { kind: "manual" };

export function AddSheet({
  genres,
  onClose,
  onAdded,
  onError,
}: {
  genres: Genre[];
  onClose: () => void;
  onAdded: (book: Book) => void;
  onError: (error: unknown) => void;
}) {
  const [step, setStep] = useState<Step>({ kind: "search" });
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Search | null>(null);
  const [searching, setSearching] = useState(false);
  const [edition, setEdition] = useState(EMPTY_EDITION);
  const [reading, setReading] = useState(EMPTY_READING);
  const [saving, setSaving] = useState(false);

  const search = useCallback(
    async (text: string) => {
      if (text.trim().length < 2) return;
      setSearching(true);
      setFound(null);
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

  const scanned = useCallback(
    (isbn: string) => {
      setQuery(isbn);
      setStep({ kind: "search" });
      void search(isbn);
    },
    [search],
  );

  function choose(candidate: FoundCandidate) {
    setReading({ ...EMPTY_READING, genre: candidate.genre_hint });
    setStep({ kind: "chosen", candidate });
  }

  async function save() {
    setSaving(true);
    try {
      if (step.kind === "chosen") {
        onAdded(await addFromCatalog(asCandidate(step.candidate), reading));
      } else {
        onAdded(await addBook(edition, reading));
      }
    } catch (error) {
      onError(error);
    } finally {
      setSaving(false);
    }
  }

  const saveable = step.kind === "chosen" || (step.kind === "manual" && edition.title.trim() !== "");

  return (
    <Sheet
      title="Añadir libro"
      onClose={onClose}
      action={
        step.kind === "chosen" || step.kind === "manual"
          ? { label: "Añadir", onClick: () => void save(), disabled: saving || !saveable }
          : undefined
      }
    >
      {step.kind === "scan" && <Scanner onIsbn={scanned} onCancel={() => setStep({ kind: "search" })} />}

      {step.kind === "search" && (
        <div className="library-fields">
          <TextField
            label="Buscar"
            type="search"
            value={query}
            onChange={setQuery}
            placeholder="título, autor o ISBN"
            autoFocus
            onSubmit={() => void search(query)}
          />
          <div className="library-actions">
            <Button variant="tinted" onClick={() => void search(query)} disabled={query.trim().length < 2}>
              Buscar
            </Button>
            <Button variant="secondary" onClick={() => setStep({ kind: "scan" })}>
              Escanear código
            </Button>
          </div>
          {searching && <Skeleton rows={3} label="Buscando" />}
          {found && failedNote(found.failed) && <Hint tone="warning">{failedNote(found.failed)}</Hint>}
          {found && found.candidates.length === 0 && !searching && (
            <Hint>No sale en ningún catálogo. Puedes teclearlo.</Hint>
          )}
          {found && found.candidates.length > 0 && (
            <List>
              {found.candidates.map((candidate) => (
                <ListRow
                  key={`${candidate.source}:${candidate.source_ref}`}
                  title={candidate.title}
                  subtitle={candidate.authors.join(", ") || undefined}
                  detail={candidateDetail(candidate)}
                  accessory="plus"
                  onClick={() => choose(candidate)}
                />
              ))}
            </List>
          )}
          <Button variant="plain" onClick={() => setStep({ kind: "manual" })}>
            Teclearlo a mano
          </Button>
        </div>
      )}

      {step.kind === "chosen" && (
        <div className="library-fields">
          <div>
            <p className="library-chosen-title">{step.candidate.title}</p>
            <Hint>{candidateDetail(step.candidate, true)}</Hint>
            {step.candidate.known_id && <Hint tone="warning">Ya está en tu biblioteca: esto será otra lectura.</Hint>}
          </div>
          <ReadingFields reading={reading} genres={genres} onChange={setReading} />
          <Button variant="plain" onClick={() => setStep({ kind: "search" })}>
            Elegir otro
          </Button>
        </div>
      )}

      {step.kind === "manual" && (
        <>
          <EditionFields edition={edition} onChange={setEdition} />
          <ReadingFields reading={reading} genres={genres} onChange={setReading} />
        </>
      )}
    </Sheet>
  );
}
