import { Button, CANNOT_UNDO, ConfirmDelete, GroupLabel, Hint, Icon, IconButton, SelectField, Sheet } from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import {
  type Booking,
  DOCUMENT_LIMIT,
  type LinkKind,
  type TripDocument,
  Unauthorised,
  documentUrl,
  readBookings,
  readDocuments,
  removeDocument,
  signIn,
  uploadDocument,
} from "./api";

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

const iconOf = (one: TripDocument) => (one.content_type.startsWith("image/") ? "image" : one.link ? "ticket" : "file");

export function DocumentsSection({ tripId }: { tripId: string }) {
  const [found, setFound] = useState<TripDocument[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<TripDocument | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readDocuments(tripId)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setFound([]);
      });
  }, [tripId]);

  if (found === null) return null;
  return (
    <section className="travel-group">
      <GroupLabel>Billetes y documentos</GroupLabel>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <ol className="surface travel-day">
        {found.map((one) => (
          <li key={one.id} className="travel-document">
            <a className="travel-document-open" href={documentUrl(tripId, one.id)} target="_blank" rel="noreferrer">
              <span className="travel-document-icon" aria-hidden="true">
                <Icon name={iconOf(one)} />
              </span>
              <span className="travel-step-text">
                <span className="travel-step-title">{one.name}</span>
                <span className="travel-step-detail">
                  {[one.link?.title, fileSize(one.size)].filter(Boolean).join(" · ")}
                </span>
              </span>
            </a>
            <IconButton icon="trash" label={`Quitar ${one.name}`} variant="plain" size="small" onClick={() => setRemoving(one)} />
          </li>
        ))}
        {found.length === 0 && <li className="travel-day-empty">El billete, la reserva del hotel, el seguro…</li>}
        <li className="travel-day-add">
          <Button variant="plain" size="small" icon="plus" onClick={() => setAdding(true)}>
            Documento
          </Button>
        </li>
      </ol>
      {adding && (
        <UploadSheet
          tripId={tripId}
          onClose={() => setAdding(false)}
          onDone={(next) => {
            setFound(next);
            setProblem("");
            setAdding(false);
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title="¿Quitar el documento?"
          subject={removing.name}
          consequence={CANNOT_UNDO}
          action="Quitar documento"
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              setFound(await removeDocument(tripId, removing.id));
              setProblem("");
            } catch (error) {
              setProblem(error instanceof Error ? error.message : "No se ha podido quitar.");
            }
            setRemoving(null);
          }}
        />
      )}
    </section>
  );
}

function UploadSheet({
  tripId,
  onClose,
  onDone,
}: {
  tripId: string;
  onClose: () => void;
  onDone: (found: TripDocument[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readBookings(tripId)
      .then(setBookings)
      .catch(() => setBookings([]));
  }, [tripId]);

  const tooBig = file !== null && file.size > DOCUMENT_LIMIT;
  const upload = async () => {
    if (!file) return;
    setBusy(true);
    const [type, id] = link ? (link.split(":") as [LinkKind, string]) : [null, null];
    try {
      onDone(await uploadDocument(tripId, file, type && id ? { type, id } : null));
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "No se ha podido subir.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      title="Nuevo documento"
      onClose={onClose}
      action={{ label: busy ? "Subiendo…" : "Subir", disabled: !file || tooBig || busy, onClick: () => void upload() }}
    >
      <div className="travel-sheet-stack">
        <input
          ref={input}
          type="file"
          accept="application/pdf,image/*"
          hidden
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <Button variant="secondary" icon="clip" onClick={() => input.current?.click()}>
          {file ? file.name : "Elegir un PDF o una foto"}
        </Button>
        {file && (
          <Hint tone={tooBig ? "warning" : undefined}>
            {tooBig ? `Pesa ${fileSize(file.size)}: el límite son 20 MB.` : fileSize(file.size)}
          </Hint>
        )}
        {bookings.length > 0 && (
          <SelectField
            label="Para"
            value={link}
            onChange={setLink}
            options={[
              { value: "", label: "Todo el viaje" },
              ...bookings.map((one) => ({
                value: `${one.type}:${one.id}`,
                label: one.day ? `${one.title} · ${one.day}` : one.title,
              })),
            ]}
          />
        )}
        {problem && <Hint tone="warning">{problem}</Hint>}
      </div>
    </Sheet>
  );
}
