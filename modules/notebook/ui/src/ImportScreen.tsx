import { Button, EmptyState, Hint, Notice, OfflineNotice, Section, TextField } from "@openarga/ui";
import * as React from "react";

import { type Imported, importNotes, uploadFile } from "./api";
import { type Vault, batches, moved, readVault, unzip } from "./vault";

interface Props {
  onDone: () => void;
}

interface Progress {
  done: number;
  total: number;
  label: string;
}

interface Result extends Imported {
  images: number;
  imageErrors: string[];
}

export function ImportScreen({ onDone }: Props) {
  const [vault, setVault] = React.useState<Vault | null>(null);
  const [failure, setFailure] = React.useState<string | null>(null);
  const [destinations, setDestinations] = React.useState<Record<string, string>>({});
  const [progress, setProgress] = React.useState<Progress | null>(null);
  const [result, setResult] = React.useState<Result | null>(null);

  const choose = async (file: File | undefined) => {
    setFailure(null);
    setResult(null);
    if (!file) return;
    try {
      const read = readVault(unzip(await file.arrayBuffer()));
      if (read.notes.length === 0) {
        setFailure("En ese .zip no hay ninguna nota (.md).");
        return;
      }
      setVault(read);
      setDestinations(Object.fromEntries(read.tops.map((top) => [top, top])));
    } catch {
      setFailure("No se ha podido leer: ¿es un .zip?");
    }
  };

  const start = async () => {
    if (!vault) return;
    const notes = vault.notes.map((note) => ({ ...note, folder: moved(note.folder, destinations) }));
    const total: Result = { created: 0, filled: 0, skipped: [], invalid: [], images: 0, imageErrors: [] };
    const steps = batches(notes, 100);
    const all = notes.length + vault.files.length;
    let done = 0;
    try {
      for (const batch of steps) {
        setProgress({ done, total: all, label: "Notas" });
        const part = await importNotes(batch);
        total.created += part.created;
        total.filled += part.filled;
        total.skipped.push(...part.skipped);
        total.invalid.push(...part.invalid);
        done += batch.length;
      }
      for (const file of vault.files) {
        setProgress({ done, total: all, label: "Imágenes" });
        try {
          const saved = await uploadFile(file.name, file.data);
          if (!saved.existed) total.images += 1;
        } catch (error) {
          total.imageErrors.push(`${file.name}: ${(error as Error).message}`);
        }
        done += 1;
      }
      setResult(total);
      setVault(null);
      onDone();
    } catch (error) {
      setFailure((error as Error).message);
    } finally {
      setProgress(null);
    }
  };

  if (result) {
    return (
      <div className="mn-import">
        <Notice tone="positive" title={`${result.created} ${result.created === 1 ? "nota importada" : "notas importadas"}`}>
          {result.images > 0 && `Y ${result.images} ${result.images === 1 ? "imagen" : "imágenes"}. `}
          {result.filled > 0 && `${result.filled} ya estaban vacías y ahora tienen su texto. `}
          {result.skipped.length > 0 && `${result.skipped.length} ya estaban y no se han tocado.`}
        </Notice>
        {result.invalid.length + result.imageErrors.length > 0 && (
          <Notice tone="warning" title="Esto no ha entrado">
            <ul className="mn-import-list">
              {result.invalid.map((one) => (
                <li key={one.path}>
                  {one.path}: {one.reason}
                </li>
              ))}
              {result.imageErrors.map((one) => (
                <li key={one}>{one}</li>
              ))}
            </ul>
          </Notice>
        )}
        <Button variant="secondary" onClick={() => setResult(null)}>
          Importar otro
        </Button>
      </div>
    );
  }

  if (!vault) {
    return (
      <div className="mn-import">
        <OfflineNotice />
        <EmptyState icon="folder" title="Trae tu vault de Obsidian">
          Comprime la carpeta del vault (en el Mac, clic derecho y «Comprimir») y elige aquí el .zip.
          Antes de guardar nada verás qué entra.
        </EmptyState>
        <label className="mn-file-pick">
          <input type="file" accept=".zip,application/zip" onChange={(event) => void choose(event.target.files?.[0])} />
          <span>Elegir el .zip</span>
        </label>
        {failure && <Notice tone="negative" title={failure} />}
      </div>
    );
  }

  return (
    <div className="mn-import">
      <dl className="mn-import-summary">
        <div>
          <dt>Notas</dt>
          <dd>{vault.notes.length}</dd>
        </div>
        <div>
          <dt>Imágenes</dt>
          <dd>{vault.files.length}</dd>
        </div>
        <div>
          <dt>Se quedan fuera</dt>
          <dd>{vault.left.length}</dd>
        </div>
      </dl>

      {vault.tops.length > 0 && (
        <Section title="Dónde cae cada carpeta">
          <Hint>Cambia la ruta para meter una carpeta dentro de otra: por ejemplo, la gramática en «Study/Alemán».</Hint>
          {vault.tops.map((top) => (
            <TextField
              key={top}
              label={top}
              value={destinations[top] ?? top}
              onChange={(value) => setDestinations((current) => ({ ...current, [top]: value }))}
            />
          ))}
        </Section>
      )}

      {vault.unresolved.length > 0 && (
        <details className="mn-import-details">
          <summary>
            {vault.unresolved.length} {vault.unresolved.length === 1 ? "enlace no encuentra" : "enlaces no encuentran"} su nota
          </summary>
          <p className="mn-import-note">Se quedan como están: cuando crees esas notas, los enlaces las encontrarán.</p>
          <ul className="mn-import-list">
            {vault.unresolved.slice(0, 50).map((target) => (
              <li key={target}>{target}</li>
            ))}
          </ul>
        </details>
      )}

      {vault.left.length > 0 && (
        <details className="mn-import-details">
          <summary>Qué se queda fuera</summary>
          <ul className="mn-import-list">
            {vault.left.slice(0, 100).map((one) => (
              <li key={one.path}>
                {one.path} · {one.reason}
              </li>
            ))}
          </ul>
        </details>
      )}

      {progress ? (
        <div className="mn-import-progress" role="status">
          <progress value={progress.done} max={progress.total} />
          <span>
            {progress.label} · {progress.done} de {progress.total}
          </span>
        </div>
      ) : (
        <div className="mn-import-actions">
          <Button variant="primary" icon="done" onClick={() => void start()}>
            Importar {vault.notes.length} notas
          </Button>
          <Button variant="plain" onClick={() => setVault(null)}>
            Elegir otro
          </Button>
        </div>
      )}
      {failure && <Notice tone="negative" title={failure} />}
    </div>
  );
}
