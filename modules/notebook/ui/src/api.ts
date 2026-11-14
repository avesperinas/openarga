import { Unauthorised, createApi, problemOf, signIn } from "@openarga/app";

export type Author = "app" | "tool" | "import";

export interface NoteSummary {
  id: string;
  folder: string;
  title: string;
  path: string;
  updated_at: string;
  updated_by: Author;
  updated_app?: string | null;
}

export interface OutlineItem {
  level: number;
  text: string;
  line: number;
}

export interface Owner {
  apps: { app: string; name: string; href: string; kind: string }[];
  properties: string[];
  day: boolean;
}

export interface Note extends NoteSummary {
  content: string;
  properties: Record<string, unknown>;
  tags: string[];
  outline: OutlineItem[];
  version: number;
  created_at: string;
  arga?: Owner | null;
}

export interface LinkOut {
  target: string;
  kind: "note" | "file" | "app";
  heading: string | null;
  alias: string | null;
  embed: boolean;
  line: number;
  note: NoteSummary | null;
}

export interface Backlink {
  note: NoteSummary;
  lines: string[];
}

export interface Links {
  links: LinkOut[];
  backlinks: Backlink[];
}

export interface Revision {
  id: string;
  title: string;
  folder: string;
  written_by: Author;
  written_at: string;
  replaced_by: Author;
  replaced_at: string;
  written_app?: string | null;
  replaced_app?: string | null;
}

export interface RevisionFull extends Revision {
  content: string;
}

export interface Tree {
  folders: string[];
  notes: NoteSummary[];
}

export interface Hit extends NoteSummary {
  snippet: string;
  tags: string[];
  href: string;
  source?: { app: string; name: string; href: string } | null;
}

export interface Trashed extends NoteSummary {
  deleted_at: string;
}

export interface TagCount {
  tag: string;
  notes: number;
}

const client = createApi("notebook");
const { get, send } = client;
const BASE = client.base;

export { Unauthorised, signIn };

export const gone = (error: unknown) => error instanceof Error && /^(no existe|not found)/.test(error.message);

export class Changed extends Error {}

const q = encodeURIComponent;

export const readTree = () => get<Tree>("/tree");
export const readNote = (id: string) => get<Note>(`/notes/${id}`);
export const readLinks = (id: string) => get<Links>(`/notes/${id}/links`);
export const resolveLink = (target: string, source?: string) =>
  get<{ note: NoteSummary | null }>(`/notes/resolve?target=${q(target)}${source ? `&source=${source}` : ""}`);
export const createNote = (folder: string, title: string, content = "") =>
  send<Note>("/notes", "POST", { folder, title, content });
export async function writeNote(id: string, content: string, version?: number): Promise<Note> {
  const response = await fetch(`${BASE}/notes/${id}`, {
    method: "PUT",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ content, version }),
  });
  if (response.status === 401) throw new Unauthorised("no session");
  if (!response.ok) {
    const problem = problemOf(await response.json().catch(() => null)) ?? `${response.status}`;
    throw response.status === 409 ? new Changed(problem) : new Error(problem);
  }
  return (await response.json()) as Note;
}
export const moveNote = (id: string, change: { folder?: string; title?: string }) =>
  send<{ note: Note; relinked: number }>(`/notes/${id}/move`, "POST", change);
export const writeProperties = (id: string, set: Record<string, unknown>, remove: string[] = []) =>
  send<Note>(`/notes/${id}/properties`, "PUT", { set, remove });
export const trashNote = (id: string) => send<void>(`/notes/${id}`, "DELETE");

export const readRevisions = (id: string) => get<Revision[]>(`/notes/${id}/revisions`);
export const readRevision = (id: string, revision: string) =>
  get<RevisionFull>(`/notes/${id}/revisions/${revision}`);
export const restoreRevision = (id: string, revision: string) =>
  send<Note>(`/notes/${id}/revisions/${revision}/restore`, "POST");

export const readTrash = () => get<Trashed[]>("/trash");
export const restoreNote = (id: string) => send<Note>(`/trash/${id}/restore`, "POST");
export const deleteForever = (id: string) => send<{ deleted: number }>(`/trash/${id}`, "DELETE");
export const emptyTrash = () => send<{ deleted: number }>("/trash", "DELETE");

export const createFolder = (path: string) => send<{ path: string }>("/folders", "POST", { path });
export const moveFolder = (from: string, to: string) =>
  send<{ path: string; notes: number }>("/folders", "PUT", { from, to });
export const deleteFolder = (path: string) => send<{ trashed: number }>(`/folders?path=${q(path)}`, "DELETE");

export function search(query: { q?: string; folder?: string; tag?: string }) {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.folder) params.set("folder", query.folder);
  if (query.tag) params.set("tag", query.tag);
  return get<Hit[]>(`/search?${params.toString()}`);
}

export interface Imported {
  created: number;
  filled: number;
  skipped: string[];
  invalid: { path: string; reason: string }[];
}

export const importNotes = (notes: { folder: string; title: string; content: string }[]) =>
  send<Imported>("/import", "POST", { notes });

export async function uploadFile(name: string, data: Uint8Array | Blob): Promise<{ name: string; existed: boolean }> {
  const response = await fetch(`${BASE}/files?name=${q(name)}`, { method: "POST", body: data as BodyInit });
  if (response.status === 401) throw new Unauthorised("no session");
  if (!response.ok) throw new Error(problemOf(await response.json().catch(() => null)) ?? `${response.status}`);
  return (await response.json()) as { name: string; existed: boolean };
}

export const fileUrl = (name: string) => `${BASE}/files/${q(name.split("/").pop() ?? name)}`;

export interface GraphNode {
  id: string;
  title: string;
  folder: string;
  links: number;
  depth: number | null;
}

export interface Graph {
  nodes: GraphNode[];
  edges: [string, string][];
}

export const readGraph = (center?: string, depth = 1) =>
  get<Graph>(center ? `/graph?center=${center}&depth=${depth}` : "/graph");

export interface Settings {
  daily_folder: string;
  review_property: string | null;
}

export const readSettings = () => get<Settings>("/settings");
export const writeSettings = (settings: Settings) => send<Settings>("/settings", "PUT", settings);
export const readPropertyNames = () => get<{ name: string; notes: number; dates: boolean }[]>("/properties");

export interface Due extends NoteSummary {
  due: string;
}

export const readReview = () => get<{ chosen: boolean; notes: Due[] }>("/review");

export interface ExportState {
  pushed_at: string | null;
  tried_at: string | null;
  outcome: "ok" | "error" | "skipped" | "unconnected" | null;
  detail: string | null;
  commit_url: string | null;
  pending: number;
}

export const readExport = () => get<ExportState>("/export");
export const pushExport = () => send<ExportState>("/export", "POST");

export interface Linkable {
  app: string;
  id: string;
  target: string;
  title: string;
  kind: string;
  href: string;
  note_id?: string | null;
}

export const readLinkables = () => get<Linkable[]>("/linkables");

export const readTags = () => get<TagCount[]>("/tags");
export const openDaily = (day?: string) => send<Note>(`/daily${day ? `?day=${day}` : ""}`, "POST");

export const readVersion = client.readVersion;
