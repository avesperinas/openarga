import { AppHeader, GroupLabel, Icon, Notice } from "@openarga/ui";
import * as React from "react";

import { type Linkable, type Links, type Note, type NoteSummary, fileUrl } from "./api";
import { argaBlock, render, slug } from "@openarga/ui/notes/markdown";
import { APP } from "./identity";
import { ago, who } from "./when";

interface Props {
  note: Note;
  links: Links | null;
  linkables?: Linkable[];
  onOpen: (note: NoteSummary, heading?: string | null) => void;
  onMissing: (target: string) => void;
  onTag: (tag: string) => void;
  onFolder: (folder: string) => void;
  onUndoClaude: () => void;
  onEdit?: () => void;
  heading?: string | null;
}

function show(value: unknown): string {
  if (Array.isArray(value)) return value.map(show).join(", ");
  if (value === true) return "Sí";
  if (value === false) return "No";
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function NoteView({ note, links, linkables = [], onOpen, onMissing, onTag, onFolder, onUndoClaude, onEdit, heading }: Props) {
  const body = React.useRef<HTMLDivElement>(null);
  const targets = React.useMemo(() => {
    const found = new Map<string, NoteSummary>();
    for (const link of links?.links ?? []) {
      if (link.note) found.set(link.target.normalize("NFC").toLowerCase(), link.note);
    }
    return found;
  }, [links]);
  const apps = React.useMemo(() => new Map(linkables.map((l) => [l.target, l])), [linkables]);
  const parts = React.useMemo(() => {
    const env = {
      resolve: (target: string) => targets.get(target.normalize("NFC").toLowerCase())?.id ?? null,
      fileUrl,
      appLink: (target: string) => apps.get(target) ?? null,
    };
    const block = argaBlock(note.content);
    if (!block) return { before: render(note.content, { ...env, title: note.title }), inner: null, after: "" };
    return {
      before: render(note.content.slice(0, block.start), { ...env, title: note.title }),
      inner: render(block.inner, env),
      after: render(note.content.slice(block.end), env),
    };
  }, [note.content, note.title, targets, apps]);
  const html = parts.before;

  React.useEffect(() => {
    if (!heading) return;
    body.current?.querySelector(`#${CSS.escape(slug(heading))}`)?.scrollIntoView({ block: "start" });
  }, [heading, html]);

  const click = (event: React.MouseEvent) => {
    const anchor = (event.target as HTMLElement).closest("a");
    if (!anchor || event.metaKey || event.ctrlKey) return;
    if (anchor.classList.contains("mn-tag")) {
      event.preventDefault();
      onTag(anchor.dataset.tag ?? "");
      return;
    }
    if (!anchor.classList.contains("mn-link")) return;
    const target = anchor.dataset.target;
    if (!target) return;
    event.preventDefault();
    const found = targets.get(target.normalize("NFC").toLowerCase());
    if (found) onOpen(found, anchor.dataset.heading ?? null);
    else onMissing(target);
  };

  const properties = Object.entries(note.properties).filter(([key]) => key !== "tags" && key !== "tag");
  const crumbs = note.folder ? note.folder.split("/") : [];

  return (
    <article className="mn-note-view">
      <div className="mn-note-head">
        <AppHeader app={APP} title={note.title} />
        {crumbs.length > 0 && (
          <nav className="mn-crumbs" aria-label="Carpeta">
            {crumbs.map((part, i) => (
              <React.Fragment key={i}>
                {i > 0 && <span className="mn-crumb-sep">/</span>}
                <button type="button" className="mn-crumb" onClick={() => onFolder(crumbs.slice(0, i + 1).join("/"))}>
                  {part}
                </button>
              </React.Fragment>
            ))}
          </nav>
        )}
        <p className="mn-note-meta">
          {who(note.updated_by, note.updated_app)} · {ago(note.updated_at)}
        </p>
      </div>

      {note.updated_by === "tool" && note.version > 1 && (
        <Notice tone="info" title="Lo último lo cambió Claude" action={{ label: "Deshacer", onClick: onUndoClaude }}>
          {ago(note.updated_at)}. Deshacerlo devuelve la nota a como estaba antes.
        </Notice>
      )}

      {(properties.length > 0 || note.tags.length > 0) && (
        <dl className="mn-properties">
          {properties.map(([key, value]) => {
            const locked = note.arga?.properties.includes(key) ?? false;
            return (
              <div className="mn-property" key={key} data-app={locked || undefined}>
                <dt title={locked ? `La pone ${owners(note)}: se cambia allí` : undefined}>{key}</dt>
                <dd>{show(value)}</dd>
              </div>
            );
          })}
          {note.tags.length > 0 && (
            <div className="mn-property">
              <dt>tags</dt>
              <dd className="mn-tags">
                {note.tags.map((tag) => (
                  <button key={tag} type="button" className="mn-tag" onClick={() => onTag(tag)}>
                    #{tag}
                  </button>
                ))}
              </dd>
            </div>
          )}
        </dl>
      )}

      <div ref={body} onClick={click} onDoubleClick={onEdit}>
        <div className="mn-prose" dangerouslySetInnerHTML={{ __html: html }} />
        {parts.inner !== null && (
          <section className="mn-arga" aria-label={note.arga ? `Lo escribe ${owners(note)}` : undefined}>
            {note.arga && <ArgaHead owner={note.arga} />}
            <div className="mn-prose" dangerouslySetInnerHTML={{ __html: parts.inner }} />
          </section>
        )}
        {parts.after.trim() && <div className="mn-prose" dangerouslySetInnerHTML={{ __html: parts.after }} />}
      </div>
      {!note.content.trim() && onEdit && (
        <button type="button" className="mn-empty-note" onClick={onEdit}>
          Esta nota está vacía. Toca para escribir.
        </button>
      )}

      <Backlinks links={links} onOpen={onOpen} />
    </article>
  );
}

export function owners(note: Note): string {
  const names = note.arga?.apps.map((app) => app.name) ?? [];
  if (names.length < 2) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} y ${names[names.length - 1]}`;
}

function ArgaHead({ owner }: { owner: NonNullable<Note["arga"]> }) {
  if (owner.day) {
    return (
      <header className="mn-arga-head">
        <span className="mn-arga-from">Lo de este día en tus apps</span>
      </header>
    );
  }
  const app = owner.apps[0]!;
  return (
    <header className="mn-arga-head">
      <span className="mn-arga-from">
        {app.kind} · {app.name}
      </span>
      <a className="mn-arga-open" href={app.href}>
        Abrir en {app.name}
        <Icon name="external" />
      </a>
    </header>
  );
}

function Backlinks({ links, onOpen }: { links: Links | null; onOpen: (note: NoteSummary) => void }) {
  if (!links) return null;
  return (
    <section className="mn-backlinks" aria-label="Enlazan aquí">
      <GroupLabel>
        {links.backlinks.length === 0
          ? "Ninguna nota enlaza aquí"
          : links.backlinks.length === 1
            ? "1 nota enlaza aquí"
            : `${links.backlinks.length} notas enlazan aquí`}
      </GroupLabel>
      <ul className="mn-backlink-list">
        {links.backlinks.map((backlink) => (
          <li key={backlink.note.id}>
            <button type="button" className="mn-backlink" onClick={() => onOpen(backlink.note)}>
              <span className="mn-backlink-title">{backlink.note.title}</span>
              {backlink.note.folder && <span className="mn-backlink-path">{backlink.note.folder}</span>}
              {backlink.lines.map((line, i) => (
                <span key={i} className="mn-backlink-line">
                  {line}
                </span>
              ))}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
