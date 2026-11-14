import { Button, EmptyState, Hint, Notice, OfflineNotice, Section, TextField } from "@openarga/ui";
import * as React from "react";

import { type Imported, importNotes, uploadFile } from "./api";
import { type Vault, batches, moved, readVault, unzip } from "./vault";
import { t } from "./lang";

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
        setFailure(t("import.no_notes"));
        return;
      }
      setVault(read);
      setDestinations(Object.fromEntries(read.tops.map((top) => [top, top])));
    } catch {
      setFailure(t("import.unreadable"));
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
        setProgress({ done, total: all, label: t("import.notes") });
        const part = await importNotes(batch);
        total.created += part.created;
        total.filled += part.filled;
        total.skipped.push(...part.skipped);
        total.invalid.push(...part.invalid);
        done += batch.length;
      }
      for (const file of vault.files) {
        setProgress({ done, total: all, label: t("import.images") });
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
        <Notice tone="positive" title={t(result.created === 1 ? "import.created.one" : "import.created.other", { count: result.created })}>
          {result.images > 0 && `${t(result.images === 1 ? "import.images_too.one" : "import.images_too.other", { count: result.images })} `}
          {result.filled > 0 && `${t("import.filled", { count: result.filled })} `}
          {result.skipped.length > 0 && t("import.skipped", { count: result.skipped.length })}
        </Notice>
        {result.invalid.length + result.imageErrors.length > 0 && (
          <Notice tone="warning" title={t("import.rejected")}>
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
          {t("import.another")}
        </Button>
      </div>
    );
  }

  if (!vault) {
    return (
      <div className="mn-import">
        <OfflineNotice />
        <EmptyState icon="folder" title={t("import.title")}>
          {t("import.how")}
        </EmptyState>
        <label className="mn-file-pick">
          <input type="file" accept=".zip,application/zip" onChange={(event) => void choose(event.target.files?.[0])} />
          <span>{t("import.choose")}</span>
        </label>
        {failure && <Notice tone="negative" title={failure} />}
      </div>
    );
  }

  return (
    <div className="mn-import">
      <dl className="mn-import-summary">
        <div>
          <dt>{t("import.notes")}</dt>
          <dd>{vault.notes.length}</dd>
        </div>
        <div>
          <dt>{t("import.images")}</dt>
          <dd>{vault.files.length}</dd>
        </div>
        <div>
          <dt>{t("import.left_out")}</dt>
          <dd>{vault.left.length}</dd>
        </div>
      </dl>

      {vault.tops.length > 0 && (
        <Section title={t("import.where")}>
          <Hint>{t("import.where_hint")}</Hint>
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
            {t(vault.unresolved.length === 1 ? "import.unresolved.one" : "import.unresolved.other", { count: vault.unresolved.length })}
          </summary>
          <p className="mn-import-note">{t("import.unresolved_detail")}</p>
          <ul className="mn-import-list">
            {vault.unresolved.slice(0, 50).map((target) => (
              <li key={target}>{target}</li>
            ))}
          </ul>
        </details>
      )}

      {vault.left.length > 0 && (
        <details className="mn-import-details">
          <summary>{t("import.what_left")}</summary>
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
            {t("import.progress", { what: progress.label, done: progress.done, total: progress.total })}
          </span>
        </div>
      ) : (
        <div className="mn-import-actions">
          <Button variant="primary" icon="done" onClick={() => void start()}>
            {t("import.start", { count: vault.notes.length })}
          </Button>
          <Button variant="plain" onClick={() => setVault(null)}>
            {t("import.choose_another")}
          </Button>
        </div>
      )}
      {failure && <Notice tone="negative" title={failure} />}
    </div>
  );
}
