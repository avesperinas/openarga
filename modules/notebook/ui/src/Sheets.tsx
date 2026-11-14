import { Button, ConfirmDelete, Icon, Sheet, TextField } from "@openarga/ui";
import * as React from "react";

import { byName, fold } from "./tree";
import { t } from "./lang";

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
    <Sheet title={t("move.title", { title })} onClose={onClose}>
      <div className="mn-sheet-body">
        <TextField label={t("move.folder")} value={query} onChange={setQuery} placeholder={t("move.folder_placeholder")} autoFocus />
        <ul className="mn-folder-pick">
          {query.trim() && !exact && (
            <li>
              <button type="button" className="mn-link-row" onClick={() => onMove(query.trim())}>
                <Icon name="plus" />
                <span className="mn-link-row-title">{t("move.create", { folder: query.trim() })}</span>
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
                <span className="mn-link-row-title">{folder || t("folder.root")}</span>
                {folder === current && <span className="mn-link-row-path">{t("move.here")}</span>}
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
        title={t("folder.confirm_delete")}
        subject={path}
        consequence={
          count > 0
            ? t(count === 1 ? "folder.delete_consequence.one" : "folder.delete_consequence.other", { count })
            : t("folder.delete_empty")
        }
        action={t("folder.delete")}
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
          {t("folder.new_note_here")}
        </Button>
        <TextField label={t("folder.path")} value={to} onChange={setTo} hint={t("folder.path_hint")} />
        <Button
          variant="secondary"
          block
          disabled={!to.trim() || to.trim() === path}
          onClick={async () => {
            await onRename(to.trim());
            onClose();
          }}
        >
          {t("folder.change_path")}
        </Button>
        <Button variant="destructive" block onClick={() => setConfirm(true)}>
          {t("folder.delete")}
        </Button>
      </div>
    </Sheet>
  );
}

export function NewFolderSheet({ base, onCreate, onClose }: { base: string; onCreate: (path: string) => Promise<void>; onClose: () => void }) {
  const [path, setPath] = React.useState(base ? `${base}/` : "");
  return (
    <Sheet
      title={t("folder.new")}
      onClose={onClose}
      action={{
        label: t("folder.create"),
        disabled: !path.trim().replace(/\/+$/, ""),
        onClick: () => void onCreate(path.trim().replace(/\/+$/, "")).then(onClose),
      }}
    >
      <div className="mn-sheet-body">
        <TextField label={t("folder.path")} value={path} onChange={setPath} autoFocus hint={t("folder.new_hint")} />
      </div>
    </Sheet>
  );
}
