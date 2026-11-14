import { currentLocale } from "./lang";
import type { NoteSummary, Tree } from "./api";

export interface FolderNode {
  path: string;
  name: string;
  folders: FolderNode[];
  notes: NoteSummary[];
  count: number;
}

const collator = () => new Intl.Collator(currentLocale(), { numeric: true, sensitivity: "base" });
export const byName = (a: string, b: string) => collator().compare(a, b);

export function build(tree: Tree): FolderNode {
  const root: FolderNode = { path: "", name: "", folders: [], notes: [], count: 0 };
  const index = new Map<string, FolderNode>([["", root]]);
  const ensure = (path: string): FolderNode => {
    const key = path.toLowerCase();
    const found = index.get(key);
    if (found) return found;
    const cut = path.lastIndexOf("/");
    const parent = ensure(cut >= 0 ? path.slice(0, cut) : "");
    const node: FolderNode = { path, name: path.slice(cut + 1), folders: [], notes: [], count: 0 };
    parent.folders.push(node);
    index.set(key, node);
    return node;
  };
  for (const folder of tree.folders) ensure(folder);
  for (const note of tree.notes) ensure(note.folder).notes.push(note);
  const sort = (node: FolderNode): number => {
    node.folders.sort((a, b) => byName(a.name, b.name));
    node.notes.sort((a, b) => byName(a.title, b.title));
    node.count = node.notes.length + node.folders.reduce((sum, child) => sum + sort(child), 0);
    return node.count;
  };
  sort(root);
  return root;
}

export function ancestors(path: string): string[] {
  if (!path) return [];
  const parts = path.split("/");
  return parts.map((_, i) => parts.slice(0, i + 1).join("/"));
}

export function filter(notes: NoteSummary[], query: string, limit = 50): NoteSummary[] {
  const wanted = fold(query.trim());
  if (!wanted) return [];
  const found = notes.filter((note) => fold(note.title).includes(wanted) || fold(note.path).includes(wanted));
  const starts = (note: NoteSummary) => (fold(note.title).startsWith(wanted) ? 0 : 1);
  return found.sort((a, b) => starts(a) - starts(b) || byName(a.title, b.title)).slice(0, limit);
}

export const fold = (text: string) =>
  text.normalize("NFD").replace(/\p{Diacritic}/gu, "").replace(/ß/g, "ss").toLowerCase();
