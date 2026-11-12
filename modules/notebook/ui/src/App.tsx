import { invalidate, mutate, prime, withTransition } from "@openarga/app";
import {
  AppHeader,
  AppShell,
  Button,
  CommandPalette,
  EmptyState,
  IconButton,
  OfflineNotice,
  type PaletteGroup,
  type PaletteItem,
  Screen,
  SETTINGS_TAB,
  Sheet,
  Skeleton,
  matching,
  useToast,
} from "@openarga/ui";
import type { Suggestions } from "@openarga/ui/notes";
import { slug } from "@openarga/ui/notes/markdown";
import * as React from "react";

import {
  type Linkable,
  type Note,
  type NoteSummary,
  type Revision,
  type Tree,
  Unauthorised,
  createFolder,
  createNote,
  deleteFolder,
  moveFolder,
  moveNote,
  openDaily,
  readLinkables,
  readLinks,
  readNote,
  readRevisions,
  readTags,
  readTree,
  restoreNote,
  restoreRevision,
  resolveLink,
  signIn,
  trashNote,
} from "./api";
import { GraphScreen } from "./GraphScreen";
import { APP } from "./identity";
import { ImportScreen, NoteEditor } from "./Lazy";
import { Pending, changed, useLoad } from "./Loads";
import { NoteView } from "./NoteView";
import { Panel, type PanelTab } from "./Panel";
import { ReviewScreen } from "./ReviewScreen";
import { type Route, pathOf, route } from "./routes";
import { SearchScreen } from "./SearchScreen";
import { SettingsScreen } from "./SettingsScreen";
import { FolderSheet, MoveSheet, NewFolderSheet } from "./Sheets";
import { Sidebar } from "./Sidebar";
import { type FolderNode, filter } from "./tree";
import { TrashScreen } from "./TrashScreen";

const WIDE = 900;
const WIDEST = 1440;
const PANEL_KEY = "notebook.panel";

type Tab = "graph" | "notes" | "today" | "search" | "review" | "settings";

function useWidth(): number {
  const [width, setWidth] = React.useState(() => window.innerWidth);
  React.useEffect(() => {
    const resize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return width;
}

function rememberedPanel(): boolean {
  try {
    return localStorage.getItem(PANEL_KEY) !== "closed";
  } catch {
    return true;
  }
}

export function freeTitle(tree: Tree | null, folder: string, base = "Sin título"): string {
  const taken = new Set(
    (tree?.notes ?? []).filter((n) => n.folder.toLowerCase() === folder.toLowerCase()).map((n) => n.title.toLowerCase()),
  );
  if (!taken.has(base.toLowerCase())) return base;
  for (let n = 2; ; n += 1) if (!taken.has(`${base} ${n}`.toLowerCase())) return `${base} ${n}`;
}

function typing(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return !!element && (element.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName));
}

function tabOf(place: Route, todayId: string | null): Tab {
  switch (place.screen) {
    case "today":
      return "today";
    case "note":
      return place.id === todayId ? "today" : "notes";
    case "search":
      return "search";
    case "review":
      return "review";
    case "settings":
      return "settings";
    case "graph":
      return "graph";
    default:
      return "notes";
  }
}

type Dialog =
  | { kind: "palette"; mode: "notes" | "commands" }
  | { kind: "move" }
  | { kind: "menu" }
  | { kind: "folder"; folder: FolderNode }
  | { kind: "new-folder"; base: string }
  | null;

interface Actions {
  go: (to: Route, replace?: boolean) => void;
  open: (note: NoteSummary, heading?: string | null) => void;
  newNote: (folder?: string, title?: string) => Promise<void>;
  fail: (error: unknown) => void;
}

export function App() {
  const toast = useToast();
  const width = useWidth();
  const wide = width >= WIDE;
  const [place, setPlace] = React.useState<Route>(() => route(window.location.pathname, window.location.search));
  const [heading, setHeading] = React.useState<string | null>(null);
  const [fresh, setFresh] = React.useState<string | null>(null);
  const [reveal, setReveal] = React.useState<string | null>(null);
  const [todayId, setTodayId] = React.useState<string | null>(null);
  const [dialog, setDialog] = React.useState<Dialog>(null);
  const [query, setQuery] = React.useState("");

  const tree = useLoad("tree", readTree, { persist: true });
  const tags = useLoad("tags", readTags, { persist: true }).data ?? [];
  const linkables = useLoad("linkables", readLinkables, { persist: true }).data ?? [];

  const fail = React.useCallback(
    (error: unknown) => {
      if (error instanceof Unauthorised) return signIn();
      toast({ message: (error as Error).message, tone: "error" });
    },
    [toast],
  );

  const go = React.useCallback((to: Route, replace = false) => {
    const path = pathOf(to);
    withTransition(() => {
      if (replace) window.history.replaceState(null, "", path);
      else if (path !== window.location.pathname + window.location.search) window.history.pushState(null, "", path);
      setPlace(to);
    });
  }, []);

  React.useEffect(() => {
    const back = () => withTransition(() => setPlace(route(window.location.pathname, window.location.search)));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  React.useEffect(() => {
    if (place.screen !== "today") return;
    openDaily()
      .then((note) => {
        prime(`note:${note.id}`, note);
        setTodayId(note.id);
        invalidate("tree");
        go({ screen: "note", id: note.id }, true);
      })
      .catch(fail);
  }, [place.screen, go, fail]);

  const open = React.useCallback(
    (note: NoteSummary, target: string | null = null) => {
      setHeading(target);
      setFresh(null);
      go({ screen: "note", id: note.id });
    },
    [go],
  );

  const noteId = place.screen === "note" ? place.id : null;
  const current = noteId ? (tree.data?.notes.find((one) => one.id === noteId) ?? null) : null;

  const newNote = React.useCallback(
    async (folder?: string, title?: string) => {
      const where = folder ?? current?.folder ?? "";
      try {
        const created = await createNote(where, title ?? freeTitle(tree.data, where));
        prime(`note:${created.id}`, created);
        invalidate("tree");
        setFresh(created.id);
        setHeading(null);
        go({ screen: "note", id: created.id });
      } catch (error) {
        fail(error);
      }
    },
    [current, tree.data, go, fail],
  );

  const actions: Actions = { go, open, newNote, fail };

  const commands = React.useMemo<PaletteItem[]>(
    () => [
      { key: "new", label: "Nota nueva", icon: "plus", shortcut: "⌥N", run: () => void newNote() },
      { key: "today", label: "Nota de hoy", icon: "today", shortcut: "⌥D", run: () => go({ screen: "today" }) },
      { key: "switch", label: "Saltar a una nota", icon: "note", shortcut: "⌘O", run: () => setDialog({ kind: "palette", mode: "notes" }) },
      { key: "search", label: "Buscar en el texto", icon: "search", shortcut: "⌘⇧F", run: () => go({ screen: "search", q: "", tag: "" }) },
      { key: "folder", label: "Carpeta nueva", icon: "folder", run: () => setDialog({ kind: "new-folder", base: current?.folder ?? "" }) },
      { key: "graph", label: "Ver el grafo", icon: "graph", shortcut: "⌥G", run: () => go({ screen: "graph" }) },
      { key: "review", label: "Para repasar", icon: "calendar", run: () => go({ screen: "review" }) },
      { key: "settings", label: "Ajustes de Notebook", icon: "settings", run: () => go({ screen: "settings" }) },
      { key: "import", label: "Importar el vault", icon: "folder", run: () => go({ screen: "import" }) },
      { key: "trash-open", label: "Abrir la papelera", icon: "trash", run: () => go({ screen: "trash" }) },
    ],
    [newNote, go, current],
  );

  React.useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (mod && key === "k") {
        event.preventDefault();
        setQuery("");
        setDialog({ kind: "palette", mode: "commands" });
      } else if (mod && key === "o") {
        event.preventDefault();
        setQuery("");
        setDialog({ kind: "palette", mode: "notes" });
      } else if (mod && event.shiftKey && key === "f") {
        event.preventDefault();
        go({ screen: "search", q: "", tag: "" });
      } else if (event.altKey && event.code === "KeyN") {
        event.preventDefault();
        void newNote();
      } else if (event.altKey && event.code === "KeyG") {
        event.preventDefault();
        go({ screen: "graph" });
      } else if (event.altKey && event.code === "KeyD") {
        event.preventDefault();
        go({ screen: "today" });
      }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [go, newNote]);

  const palette = React.useMemo<PaletteGroup[]>(() => {
    if (dialog?.kind !== "palette") return [];
    const notes = tree.data?.notes ?? [];
    const found = query.trim()
      ? filter(notes, query, 30)
      : [...notes].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 12);
    const noteItems: PaletteItem[] = found.map((note) => ({
      key: `n-${note.id}`,
      label: note.title,
      detail: note.folder || undefined,
      icon: "note",
      run: () => open(note),
    }));
    if (dialog.mode === "notes") return [{ label: "Notas", items: noteItems }];
    const words = query.trim();
    return [
      { label: "Comandos", items: matching(commands, query) },
      { label: "Notas", items: noteItems },
      {
        label: "En el texto",
        items: words
          ? [{ key: "search", label: `Buscar «${words}» en el texto`, icon: "search", run: () => go({ screen: "search", q: words, tag: "" }) }]
          : [],
      },
    ];
  }, [dialog, tree.data, query, commands, open, go]);

  const sidebar = (
    <Sidebar
      tree={tree.data}
      found={tree.found}
      active={noteId}
      activeFolder={reveal ?? current?.folder ?? null}
      onOpen={(note) => open(note)}
      onSearch={(q) => go({ screen: "search", q, tag: "" })}
      onTrash={() => go({ screen: "trash" })}
      onImport={() => go({ screen: "import" })}
      onGraph={() => go({ screen: "graph" })}
      onCommands={() => {
        setQuery("");
        setDialog({ kind: "palette", mode: "commands" });
      }}
      onNewNote={() => void newNote("")}
      onNewFolder={() => setDialog({ kind: "new-folder", base: "" })}
      onFolderMenu={(folder) => setDialog({ kind: "folder", folder })}
    />
  );

  const backToNotes = { label: "Notas", onClick: () => go({ screen: "home" }) };
  let main: React.ReactNode;
  switch (place.screen) {
    case "search":
      main = (
        <Screen>
          <AppHeader app={APP} title="Buscar" />
          <SearchScreen
            query={place.q}
            tag={place.tag}
            onQuery={(q, tag) => go({ screen: "search", q, tag }, true)}
            onOpen={(note) => open(note)}
          />
        </Screen>
      );
      break;
    case "review":
      main = (
        <Screen>
          <AppHeader app={APP} title="Para repasar" />
          <ReviewScreen onOpen={(note) => open(note)} onSettings={() => go({ screen: "settings" })} />
        </Screen>
      );
      break;
    case "settings":
      main = <SettingsScreen />;
      break;
    case "trash":
      main = (
        <Screen>
          <AppHeader app={APP} title="Papelera" back={backToNotes} />
          <TrashScreen onBack={backToNotes.onClick} />
        </Screen>
      );
      break;
    case "import":
      main = (
        <Screen>
          <AppHeader app={APP} title="Importar el vault" back={backToNotes} />
          <ImportScreen onDone={changed} />
        </Screen>
      );
      break;
    case "graph":
      main = (
        <Screen wide>
          <AppHeader app={APP} title="Notebook" />
          <GraphScreen onOpen={(id) => go({ screen: "note", id })} onNewNote={() => void newNote("")} />
        </Screen>
      );
      break;
    case "today":
      main = (
        <Screen label="Nota de hoy">
          <AppHeader app={APP} title="Hoy" />
          <Skeleton rows={8} />
        </Screen>
      );
      break;
    default:
      main = sidebar;
  }

  let detail: React.ReactNode = undefined;
  if (place.screen === "note") {
    detail = (
      <NoteScreen
        key={place.id}
        id={place.id}
        width={width}
        heading={heading}
        fresh={fresh === place.id}
        tree={tree.data}
        tags={tags.map((t) => t.tag)}
        linkables={linkables}
        actions={actions}
        dialog={dialog}
        setDialog={setDialog}
        onReveal={(folder) => {
          setReveal(folder);
          if (!wide) go({ screen: "home" });
        }}
      />
    );
  } else if (wide && place.screen === "home" && tree.data) {
    const empty = tree.data.notes.length === 0;
    detail = (
      <Screen label="Ninguna nota abierta">
        <EmptyState
          icon="note"
          title={empty ? "Aún no hay notas" : "Elige una nota"}
          action={{ label: "Nota nueva", icon: "plus", onClick: () => void newNote("") }}
        >
          {empty
            ? "Escribe la primera, pídesela a Claude o importa tu vault de Obsidian."
            : `${tree.data.notes.length} notas en ${tree.data.folders.length} carpetas. ⌘O para saltar a una, ⌘K para todo lo demás.`}
        </EmptyState>
      </Screen>
    );
  }

  return (
    <div className="mn">
      <AppShell
        label="Secciones"
        active={tabOf(place, todayId)}
        onSelect={(tab) =>
          go(
            tab === "notes"
              ? { screen: "home" }
              : tab === "search"
                ? { screen: "search", q: "", tag: "" }
                : { screen: tab },
          )
        }
        tabs={[
          { id: "graph", label: "Grafo", icon: "graph" },
          { id: "notes", label: "Notas", icon: "note" },
          { id: "today", label: "Hoy", icon: "today" },
          { id: "search", label: "Buscar", icon: "search" },
          { id: "review", label: "Repasar", icon: "calendar" },
          SETTINGS_TAB,
        ]}
        detail={detail}
      >
        {main}
      </AppShell>

      {dialog?.kind === "palette" && (
        <CommandPalette
          label={dialog.mode === "notes" ? "Saltar a una nota" : "Comandos y notas"}
          placeholder={dialog.mode === "notes" ? "Título de la nota" : "Qué quieres hacer, o una nota"}
          query={query}
          onQuery={setQuery}
          groups={palette}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "folder" && (
        <FolderSheet
          path={dialog.folder.path}
          count={dialog.folder.count}
          onNewNote={() => {
            setDialog(null);
            void newNote(dialog.folder.path);
          }}
          onRename={async (to) => {
            try {
              await moveFolder(dialog.folder.path, to);
              changed();
            } catch (error) {
              fail(error);
            }
          }}
          onDelete={async () => {
            const { trashed } = await deleteFolder(dialog.folder.path);
            changed();
            toast({ message: trashed ? `${trashed} ${trashed === 1 ? "nota" : "notas"} a la papelera` : "Carpeta borrada" });
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "new-folder" && (
        <NewFolderSheet
          base={dialog.base}
          onCreate={async (path) => {
            try {
              const made = await createFolder(path);
              invalidate("tree");
              setReveal(made.path);
            } catch (error) {
              fail(error);
            }
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

function NoteScreen({
  id,
  width,
  heading,
  fresh,
  tree,
  tags,
  linkables,
  actions,
  dialog,
  setDialog,
  onReveal,
}: {
  id: string;
  width: number;
  heading: string | null;
  fresh: boolean;
  tree: Tree | null;
  tags: string[];
  linkables: Linkable[];
  actions: Actions;
  dialog: Dialog;
  setDialog: (dialog: Dialog) => void;
  onReveal: (folder: string) => void;
}) {
  const toast = useToast();
  const { go, open, newNote, fail } = actions;
  const { data: note, found } = useLoad(`note:${id}`, () => readNote(id), { staleMs: 0 });
  const links = useLoad(`links:${id}`, () => readLinks(id), { staleMs: 0 }).data;
  const [editing, setEditing] = React.useState(fresh);
  const [panelPref, setPanelPref] = React.useState(rememberedPanel);
  const [panelTab, setPanelTab] = React.useState<PanelTab>("outline");
  const [sheet, setSheet] = React.useState(false);
  const side = width >= WIDEST;
  const panelOpen = side && panelPref && !!note;

  const saved = React.useCallback(
    (next: Note) => {
      prime(`note:${id}`, next);
    },
    [id],
  );

  const wasEditing = React.useRef(editing);
  React.useEffect(() => {
    if (wasEditing.current && !editing) {
      invalidate(`links:${id}`);
      invalidate("tree");
    }
    wasEditing.current = editing;
  }, [editing, id]);

  const missingLink = React.useCallback(
    (target: string) => {
      const name = target.split("/").pop() ?? target;
      const folder = target.includes("/") ? target.slice(0, target.lastIndexOf("/")) : (note?.folder ?? "");
      toast({ message: `«${name}» aún no existe`, action: { label: "Crearla", run: () => void newNote(folder, name) } });
    },
    [note, toast, newNote],
  );

  const followLink = React.useCallback(
    async (target: string, part: string | null) => {
      if (!target) {
        if (part) document.getElementById(slug(part))?.scrollIntoView({ behavior: "smooth" });
        return;
      }
      try {
        const { note: found } = await resolveLink(target, id);
        if (found) open(found, part);
        else if (/^[a-z][a-z0-9_]*:/.test(target)) {
          const app = linkables.find((one) => one.target === target);
          if (app) window.location.assign(app.href);
          else toast({ message: "Eso ya no está en su app" });
        } else missingLink(target);
      } catch (error) {
        fail(error);
      }
    },
    [id, open, missingLink, fail, linkables, toast],
  );

  const restore = React.useCallback(
    async (revision: Revision) => {
      try {
        await mutate(`note:${id}`, undefined, { request: () => restoreRevision(id, revision.id) });
        changed();
        toast({ message: "Vuelta a la versión de antes" });
      } catch (error) {
        fail(error);
      }
    },
    [id, toast, fail],
  );

  const undoClaude = React.useCallback(async () => {
    try {
      const [latest] = await readRevisions(id);
      if (!latest || latest.replaced_by !== "tool") {
        toast({ message: "No hay un cambio de Claude que deshacer" });
        return;
      }
      await restore(latest);
    } catch (error) {
      fail(error);
    }
  }, [id, restore, toast, fail]);

  const trash = React.useCallback(async () => {
    if (!note) return;
    try {
      await trashNote(note.id);
      setDialog(null);
      changed();
      go({ screen: "home" }, true);
      toast({
        message: `A la papelera · ${note.title}`,
        action: {
          label: "Deshacer",
          run: () =>
            void restoreNote(note.id).then(() => {
              changed();
              go({ screen: "note", id: note.id });
            }),
        },
      });
    } catch (error) {
      fail(error);
    }
  }, [note, setDialog, go, toast, fail]);

  const moveTo = React.useCallback(
    async (folder: string) => {
      try {
        const { note: moved, relinked } = await moveNote(id, { folder });
        setDialog(null);
        prime(`note:${id}`, moved);
        changed();
        toast({
          message: relinked ? `Movida · ${relinked} ${relinked === 1 ? "nota" : "notas"} con enlaces arreglados` : "Movida",
        });
      } catch (error) {
        fail(error);
      }
    },
    [id, setDialog, toast, fail],
  );

  const renamed = React.useCallback(
    (next: Note, relinked: number) => {
      saved(next);
      invalidate("tree");
      if (relinked) toast({ message: `Renombrada · ${relinked} ${relinked === 1 ? "nota" : "notas"} con enlaces arreglados` });
    },
    [saved, toast],
  );

  const suggestions = React.useCallback(
    (): Suggestions => ({
      notes: (tree?.notes ?? []).map((n) => ({ title: n.title, folder: n.folder })),
      tags,
      links: linkables.map((l) => ({ target: l.target, title: l.title, kind: l.kind })),
    }),
    [tree, tags, linkables],
  );

  const togglePanel = React.useCallback(() => {
    setPanelPref((now) => {
      try {
        localStorage.setItem(PANEL_KEY, now ? "closed" : "open");
      } catch {
      }
      return !now;
    });
  }, []);

  const showHistory = React.useCallback(() => {
    setDialog(null);
    setPanelTab("history");
    if (side) setPanelPref(true);
    else setSheet(true);
  }, [side, setDialog]);

  React.useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey;
      const key = event.key.toLowerCase();
      if (!note) return;
      if (mod && key === "e") {
        event.preventDefault();
        setEditing((e) => !e);
      } else if (!mod && !event.altKey && key === "e" && !editing && !dialog && !typing(event.target)) {
        event.preventDefault();
        setEditing(true);
      } else if (key === "escape" && editing && !dialog && !document.querySelector(".cm-tooltip-autocomplete")) {
        setEditing(false);
      }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [note, editing, dialog]);

  const jumpTo = (text: string) => {
    document.getElementById(slug(text))?.scrollIntoView({ behavior: "smooth", block: "start" });
    setSheet(false);
  };

  const panel = note && (
    <Panel
      note={note}
      links={links}
      tab={panelTab}
      onTab={setPanelTab}
      onOpen={open}
      onHeading={jumpTo}
      onRestore={restore}
    />
  );

  return (
    <div className="mn-note-screen" data-panel={panelOpen || undefined}>
      <div className="mn-note-main">
        <div className="mn-toolbar">
          <Button size="small" variant="plain" icon="chevron-left" onClick={() => go({ screen: "home" })}>
            Notas
          </Button>
          <span className="mn-toolbar-space" />
          {note && (
            <>
              <Button size="small" variant={editing ? "primary" : "secondary"} icon={editing ? "done" : "edit"} onClick={() => setEditing((e) => !e)}>
                {editing ? "Hecho" : "Editar"}
              </Button>
              <IconButton icon="settings" label="Más de esta nota" variant="plain" onClick={() => setDialog({ kind: "menu" })} />
              <IconButton
                icon="sidebar"
                label={side ? (panelOpen ? "Plegar el panel" : "Desplegar el panel") : "Índice, enlaces e historial"}
                variant="plain"
                onClick={side ? togglePanel : () => setSheet(true)}
              />
            </>
          )}
        </div>
        <Screen label={note?.title ?? "Nota"}>
          <OfflineNotice />
          {!note ? (
            <Pending found={found} missing="Esta nota ya no está" />
          ) : editing ? (
            <NoteEditor
              key={note.id}
              note={note}
              suggestions={suggestions}
              onSaved={saved}
              onRenamed={renamed}
              onOpenLink={(target, part) => void followLink(target, part)}
              onTag={(tag) => go({ screen: "search", q: "", tag })}
              focusTitle={fresh}
            />
          ) : (
            <NoteView
              note={note}
              links={links}
              linkables={linkables}
              heading={heading}
              onOpen={open}
              onMissing={missingLink}
              onTag={(tag) => go({ screen: "search", q: "", tag })}
              onFolder={onReveal}
              onUndoClaude={() => void undoClaude()}
              onEdit={() => setEditing(true)}
            />
          )}
        </Screen>
      </div>
      {panelOpen && (
        <aside className="mn-panel" aria-label="De esta nota">
          {panel}
        </aside>
      )}
      {!panelOpen && sheet && panel && (
        <Sheet title={note!.title} onClose={() => setSheet(false)}>
          {panel}
        </Sheet>
      )}
      {dialog?.kind === "move" && note && (
        <MoveSheet
          title={note.title}
          folders={tree?.folders ?? []}
          current={note.folder}
          onMove={(folder) => void moveTo(folder)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "menu" && note && (
        <Sheet title={note.title} onClose={() => setDialog(null)}>
          <div className="mn-sheet-body">
            <Button block icon="folder" onClick={() => setDialog({ kind: "move" })}>
              Mover a otra carpeta
            </Button>
            <Button block icon="clock" onClick={showHistory}>
              Historial
            </Button>
            <Button block variant="destructive" icon="trash" onClick={() => void trash()}>
              Enviar a la papelera
            </Button>
          </div>
        </Sheet>
      )}
    </div>
  );
}

