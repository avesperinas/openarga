import { Button, CANNOT_UNDO, ConfirmDelete, Icon, Sheet, TextField } from "@openarga/ui";
import * as React from "react";

import { byName, fold } from "./tree";

export function MoveSheet({
  title,
  folders,
  current,
  onMove,
  onClose,
}: {
  title: string;
  folders: string[];
  current: string;
  onMove: (folder: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = React.useState("");
  const words = fold(query.trim());
  const shown = ["", ...[...folders].sort(byName)].filter((folder) => !words || fold(folder).includes(words));
  const exact = folders.some((folder) => folder.toLowerCase() === query.trim().toLowerCase());
  return (
    <Sheet title={`Mover «${title}»`} onClose={onClose}>
      <div className="mn-sheet-body">
        <TextField label="Carpeta" value={query} onChange={setQuery} placeholder="Busca o escribe una nueva" autoFocus />
        <ul className="mn-folder-pick">
          {query.trim() && !exact && (
            <li>
              <button type="button" className="mn-link-row" onClick={() => onMove(query.trim())}>
                <Icon name="plus" />
                <span className="mn-link-row-title">Crear «{query.trim()}» y moverla ahí</span>
              </button>
            </li>
          )}
          {shown.map((folder) => (
            <li key={folder || "/"}>
              <button
                type="button"
                className="mn-link-row"
                disabled={folder === current}
                onClick={() => onMove(folder)}
              >
                <Icon name="folder" />
                <span className="mn-link-row-title">{folder || "La raíz"}</span>
                {folder === current && <span className="mn-link-row-path">aquí está</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Sheet>
  );
}

export function FolderSheet({
  path,
  count,
  onNewNote,
  onRename,
  onDelete,
  onClose,
}: {
  path: string;
  count: number;
  onNewNote: () => void;
  onRename: (to: string) => Promise<void>;
  onDelete: () => Promise<void>;
  onClose: () => void;
}) {
  const [to, setTo] = React.useState(path);
  const [confirm, setConfirm] = React.useState(false);
  if (confirm) {
    return (
      <ConfirmDelete
        title="¿Borrar esta carpeta?"
        subject={path}
        consequence={
          count > 0
            ? `${count} ${count === 1 ? "nota va" : "notas van"} a la papelera, de donde se recuperan. La carpeta y sus subcarpetas desaparecen.`
            : `Está vacía. ${CANNOT_UNDO}`
        }
        action="Borrar carpeta"
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          await onDelete();
          onClose();
        }}
      />
    );
  }
  return (
    <Sheet title={path} onClose={onClose}>
      <div className="mn-sheet-body">
        <Button variant="tinted" icon="plus" block onClick={onNewNote}>
          Nota nueva aquí
        </Button>
        <TextField label="Ruta" value={to} onChange={setTo} hint="Cámbiala para renombrarla o moverla, con todo lo de dentro." />
        <Button
          variant="secondary"
          block
          disabled={!to.trim() || to.trim() === path}
          onClick={async () => {
            await onRename(to.trim());
            onClose();
          }}
        >
          Cambiar la ruta
        </Button>
        <Button variant="destructive" block onClick={() => setConfirm(true)}>
          Borrar carpeta
        </Button>
      </div>
    </Sheet>
  );
}

export function NewFolderSheet({ base, onCreate, onClose }: { base: string; onCreate: (path: string) => Promise<void>; onClose: () => void }) {
  const [path, setPath] = React.useState(base ? `${base}/` : "");
  return (
    <Sheet
      title="Carpeta nueva"
      onClose={onClose}
      action={{
        label: "Crear carpeta",
        disabled: !path.trim().replace(/\/+$/, ""),
        onClick: () => void onCreate(path.trim().replace(/\/+$/, "")).then(onClose),
      }}
    >
      <div className="mn-sheet-body">
        <TextField label="Ruta" value={path} onChange={setPath} autoFocus hint="Con / para meterla dentro de otra: Study/Alemán" />
      </div>
    </Sheet>
  );
}
