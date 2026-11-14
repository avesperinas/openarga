import { Button, ConfirmDelete, EmptyState, IconButton, OfflineNotice, useToast } from "@openarga/ui";
import * as React from "react";

import { type Trashed, deleteForever, emptyTrash, readTrash, restoreNote } from "./api";
import { Pending, changed, useLoad } from "./Loads";
import { ago } from "./when";
import { t } from "./lang";

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
      toast({ message: t("trash.restored", { title: note.title }) });
      load();
    } catch (error) {
      toast({ message: (error as Error).message, tone: "error" });
    }
  };

  if (notes === null) return <Pending found={found} />;
  if (notes.length === 0) {
    return (
      <EmptyState icon="trash" title={t("trash.empty")} action={{ label: t("trash.back"), onClick: onBack }}>
        {t("trash.empty_detail")}
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
                {note.folder ? `${note.folder} · ` : ""}
                {t("trash.deleted", { when: ago(note.deleted_at) })}
              </span>
            </div>
            <Button size="small" variant="tinted" icon="undo" onClick={() => void restore(note)}>
              {t("trash.restore")}
            </Button>
            <IconButton icon="trash" label={t("trash.delete_named", { title: note.title })} variant="plain" size="small" onClick={() => setConfirm(note)} />
          </li>
        ))}
      </ul>
      <Button variant="destructive" block onClick={() => setConfirm("all")}>
        {t("trash.empty_all")}
      </Button>
      {confirm && (
        <ConfirmDelete
          title={confirm === "all" ? t("trash.confirm_all") : t("trash.confirm_one")}
          subject={confirm === "all" ? t(notes.length === 1 ? "count.notes.one" : "count.notes.other", { count: notes.length }) : confirm.title}
          consequence={t("trash.consequence")}
          action={confirm === "all" ? t("trash.empty_all") : t("trash.delete_forever")}
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
