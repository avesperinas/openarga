import { Button, CANNOT_UNDO, ConfirmDelete, EmptyState, IconButton, OfflineNotice, useToast } from "@openarga/ui";
import * as React from "react";

import { type Trashed, deleteForever, emptyTrash, readTrash, restoreNote } from "./api";
import { Pending, changed, useLoad } from "./Loads";
import { ago } from "./when";

interface Props {
  onBack: () => void;
}

export function TrashScreen({ onBack }: Props) {
  const toast = useToast();
  const { data: notes, found } = useLoad("trash", readTrash);
  const [confirm, setConfirm] = React.useState<Trashed | "all" | null>(null);
  const load = changed;

  const restore = async (note: Trashed) => {
    try {
      await restoreNote(note.id);
      toast({ message: `Recuperada · ${note.title}` });
      load();
    } catch (error) {
      toast({ message: (error as Error).message, tone: "error" });
    }
  };

  if (notes === null) return <Pending found={found} />;
  if (notes.length === 0) {
    return (
      <EmptyState icon="trash" title="La papelera está vacía" action={{ label: "Volver a las notas", onClick: onBack }}>
        Lo que borres en Notebook viene aquí, y de aquí se recupera.
      </EmptyState>
    );
  }

  return (
    <div className="mn-trash">
      <OfflineNotice />
      <ul className="mn-hits">
        {notes.map((note) => (
          <li key={note.id} className="mn-trash-row">
            <div className="mn-trash-text">
              <span className="mn-hit-title">{note.title}</span>
              <span className="mn-hit-path">
                {note.folder ? `${note.folder} · ` : ""}borrada {ago(note.deleted_at)}
              </span>
            </div>
            <Button size="small" variant="tinted" icon="undo" onClick={() => void restore(note)}>
              Recuperar
            </Button>
            <IconButton icon="trash" label={`Borrar para siempre «${note.title}»`} variant="plain" size="small" onClick={() => setConfirm(note)} />
          </li>
        ))}
      </ul>
      <Button variant="destructive" block onClick={() => setConfirm("all")}>
        Vaciar la papelera
      </Button>
      {confirm && (
        <ConfirmDelete
          title={confirm === "all" ? "¿Vaciar la papelera?" : "¿Borrar esta nota para siempre?"}
          subject={confirm === "all" ? `${notes.length} ${notes.length === 1 ? "nota" : "notas"}` : confirm.title}
          consequence={`Se pierden con su historial. ${CANNOT_UNDO}`}
          action={confirm === "all" ? "Vaciar la papelera" : "Borrar para siempre"}
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            if (confirm === "all") await emptyTrash();
            else await deleteForever(confirm.id);
            setConfirm(null);
            load();
          }}
        />
      )}
    </div>
  );
}
