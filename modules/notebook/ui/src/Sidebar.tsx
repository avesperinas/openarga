import { AppHeader, Button, EmptyState, Icon, IconButton, OfflineNotice, Screen, SearchField } from "@openarga/ui";
import * as React from "react";

import type { NoteSummary, Tree } from "./api";
import { APP } from "./identity";
import { Pending } from "./Loads";
import { type FolderNode, ancestors, build, filter } from "./tree";

const OPEN_KEY = "notebook.open-folders";

function remembered(): Set<string> {
  try {
    const raw = localStorage.getItem(OPEN_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function remember(open: Set<string>): void {
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify([...open]));
  } catch {
  }
}

interface Props {
  tree: Tree | null;
  found: { error: Error | null; refresh: () => Promise<void> };
  active: string | null;
  activeFolder: string | null;
  onOpen: (note: NoteSummary) => void;
  onSearch: (query: string) => void;
  onTrash: () => void;
  onImport: () => void;
  onGraph: () => void;
  onCommands: () => void;
  onNewNote: () => void;
  onNewFolder: () => void;
  onFolderMenu: (folder: FolderNode) => void;
}

export function Sidebar({
  tree,
  found,
  active,
  activeFolder,
  onOpen,
  onSearch,
  onTrash,
  onImport,
  onGraph,
  onCommands,
  onNewNote,
  onNewFolder,
  onFolderMenu,
}: Props) {
  const [open, setOpen] = React.useState<Set<string>>(remembered);
  const [query, setQuery] = React.useState("");
  const root = React.useMemo(() => (tree ? build(tree) : null), [tree]);
  const matches = React.useMemo(() => (tree ? filter(tree.notes, query) : []), [tree, query]);

  React.useEffect(() => {
    if (activeFolder === null) return;
    setOpen((current) => {
      const needed = ancestors(activeFolder).filter((path) => !current.has(path.toLowerCase()));
      if (!needed.length) return current;
      const next = new Set(current);
      for (const path of needed) next.add(path.toLowerCase());
      remember(next);
      return next;
    });
  }, [activeFolder]);

  const toggle = React.useCallback((path: string) => {
    setOpen((current) => {
      const next = new Set(current);
      const key = path.toLowerCase();
      if (next.has(key)) next.delete(key);
      else next.add(key);
      remember(next);
      return next;
    });
  }, []);

  return (
    <Screen>
      <AppHeader app={APP} title="Notas" />
      <OfflineNotice />
      <div className="mn-create">
        <Button variant="primary" icon="plus" size="small" onClick={onNewNote}>
          Nota nueva
        </Button>
        <IconButton icon="folder" label="Carpeta nueva" size="small" onClick={onNewFolder} />
        <IconButton icon="search" label="Comandos (⌘K)" size="small" onClick={onCommands} />
      </div>
      <form
        className="mn-filter"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) onSearch(query.trim());
        }}
      >
        <SearchField value={query} onChange={setQuery} placeholder="Buscar notas" label="Buscar notas" />
      </form>
      <nav className="mn-shortcuts" aria-label="Atajos">
        <button type="button" className="mn-shortcut" onClick={onGraph}>
          <Icon name="graph" />
          Grafo
        </button>
        <button type="button" className="mn-shortcut" onClick={onTrash}>
          <Icon name="trash" />
          Papelera
        </button>
        <button type="button" className="mn-shortcut" onClick={onImport}>
          <Icon name="folder" />
          Importar el vault
        </button>
      </nav>
      {query.trim() ? (
        <div className="mn-matches">
          <ul className="mn-tree" aria-label="Notas que coinciden">
            {matches.map((note) => (
              <li key={note.id}>
                <NoteRow note={note} active={note.id === active} onOpen={onOpen} depth={0} path />
              </li>
            ))}
          </ul>
          <button type="button" className="mn-search-all" onClick={() => onSearch(query.trim())}>
            <Icon name="search" />
            Buscar «{query.trim()}» en el texto
          </button>
        </div>
      ) : root ? (
        root.count === 0 ? (
          <EmptyState icon="note" title="Aún no hay notas" action={{ label: "Nota nueva", icon: "plus", onClick: onNewNote }}>
            Escribe la primera, pídesela a Claude o importa tu vault de Obsidian.
          </EmptyState>
        ) : (
          <ul className="mn-tree" aria-label="Notas">
            <Folder node={root} depth={-1} open={open} toggle={toggle} active={active} onOpen={onOpen} onMenu={onFolderMenu} />
          </ul>
        )
      ) : (
        <Pending found={found} rows={8} />
      )}
    </Screen>
  );
}

function Folder({
  node,
  depth,
  open,
  toggle,
  active,
  onOpen,
  onMenu,
}: {
  node: FolderNode;
  depth: number;
  open: Set<string>;
  toggle: (path: string) => void;
  active: string | null;
  onOpen: (note: NoteSummary) => void;
  onMenu: (folder: FolderNode) => void;
}) {
  const expanded = depth < 0 || open.has(node.path.toLowerCase());
  const children = expanded && (
    <>
      {node.folders.map((child) => (
        <li key={child.path}>
          <Folder node={child} depth={depth + 1} open={open} toggle={toggle} active={active} onOpen={onOpen} onMenu={onMenu} />
        </li>
      ))}
      {node.notes.map((note) => (
        <li key={note.id}>
          <NoteRow note={note} active={note.id === active} onOpen={onOpen} depth={depth + 1} />
        </li>
      ))}
    </>
  );
  if (depth < 0) return children;
  return (
    <>
      <div className="mn-folder-line">
        <button
          type="button"
          className="mn-row mn-folder"
          style={{ "--depth": depth } as React.CSSProperties}
          aria-expanded={expanded}
          onClick={() => toggle(node.path)}
        >
          <span className="mn-chevron" data-open={expanded || undefined}>
            <Icon name="chevron-right" />
          </span>
          <span className="mn-row-name">{node.name}</span>
          <span className="mn-row-count">{node.count}</span>
        </button>
        <span className="mn-folder-menu">
          <IconButton icon="settings" label={`Carpeta ${node.name}`} variant="plain" size="small" onClick={() => onMenu(node)} />
        </span>
      </div>
      {expanded && <ul className="mn-tree">{children}</ul>}
    </>
  );
}

function NoteRow({
  note,
  active,
  onOpen,
  depth,
  path = false,
}: {
  note: NoteSummary;
  active: boolean;
  onOpen: (note: NoteSummary) => void;
  depth: number;
  path?: boolean;
}) {
  return (
    <a
      className="mn-row mn-note"
      href={`/notebook/nota/${note.id}`}
      style={{ "--depth": depth } as React.CSSProperties}
      aria-current={active ? "page" : undefined}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        event.preventDefault();
        onOpen(note);
      }}
    >
      <span className="mn-row-name">{note.title}</span>
      {path && note.folder && <span className="mn-row-path">{note.folder}</span>}
      {note.updated_by === "tool" && <span className="mn-by-claude" title="Lo último lo cambió Claude" />}
    </a>
  );
}
