import { Button, Icon, SegmentedControl, Skeleton } from "@openarga/ui";
import * as React from "react";

import {
  type Graph,
  type Links,
  type Note,
  type NoteSummary,
  type Revision,
  type RevisionFull,
  readGraph,
  readRevision,
  readRevisions,
} from "./api";
import { GraphView } from "./Lazy";
import { diff, hunks } from "./diff";
import { render } from "@openarga/ui/notes/markdown";
import { ago } from "./when";
import { t } from "./lang";

export type PanelTab = "outline" | "links" | "graph" | "history";

const TABS = () => [
  { value: "outline" as const, label: t("panel.outline") },
  { value: "links" as const, label: t("panel.links") },
  { value: "graph" as const, label: t("sidebar.graph") },
  { value: "history" as const, label: t("panel.history") },
];

interface Props {
  note: Note;
  links: Links | null;
  tab: PanelTab;
  onTab: (tab: PanelTab) => void;
  onOpen: (note: NoteSummary, heading?: string | null) => void;
  onHeading: (text: string) => void;
  onRestore: (revision: Revision) => Promise<void>;
}

export function Panel({ note, links, tab, onTab, onOpen, onHeading, onRestore }: Props) {
  return (
    <div className="mn-panel-inner">
      <SegmentedControl label={t("panel.show")} options={TABS()} value={tab} onChange={onTab} />
      {tab === "outline" && <Outline note={note} onHeading={onHeading} />}
      {tab === "links" && <Outgoing links={links} onOpen={onOpen} />}
      {tab === "graph" && <LocalGraph note={note} links={links} onOpen={(id) => onOpen({ ...note, id })} />}
      {tab === "history" && <History note={note} onRestore={onRestore} />}
    </div>
  );
}

function Outline({ note, onHeading }: { note: Note; onHeading: (text: string) => void }) {
  if (note.outline.length === 0) return <p className="mn-panel-empty">{t("panel.no_headings")}</p>;
  const top = Math.min(...note.outline.map((h) => h.level));
  return (
    <ul className="mn-outline">
      {note.outline.map((heading, i) => (
        <li key={i}>
          <button
            type="button"
            className="mn-outline-item"
            style={{ "--depth": heading.level - top } as React.CSSProperties}
            onClick={() => onHeading(heading.text)}
          >
            {heading.text}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Outgoing({ links, onOpen }: { links: Links | null; onOpen: (note: NoteSummary, heading?: string | null) => void }) {
  if (!links) return <Skeleton rows={3} />;
  const notes = links.links.filter((link) => link.kind === "note");
  const seen = new Set<string>();
  const unique = notes.filter((link) => {
    const key = link.note?.id ?? `?${link.target.toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const existing = unique.filter((link) => link.note);
  const missing = unique.filter((link) => !link.note);
  if (unique.length === 0) return <p className="mn-panel-empty">{t("panel.no_links")}</p>;
  return (
    <div className="mn-outgoing">
      {existing.length > 0 && (
        <ul className="mn-link-list">
          {existing.map((link) => (
            <li key={link.note!.id}>
              <button type="button" className="mn-link-row" onClick={() => onOpen(link.note!, link.heading)}>
                <Icon name="note" />
                <span className="mn-link-row-title">{link.note!.title}</span>
                {link.note!.folder && <span className="mn-link-row-path">{link.note!.folder}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {missing.length > 0 && (
        <>
          <p className="mn-panel-label">{t("panel.missing")}</p>
          <ul className="mn-link-list">
            {missing.map((link) => (
              <li key={link.target} className="mn-link-row" data-missing="">
                <Icon name="note" />
                <span className="mn-link-row-title">{link.target}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function History({ note, onRestore }: { note: Note; onRestore: (revision: Revision) => Promise<void> }) {
  const [revisions, setRevisions] = React.useState<Revision[] | null>(null);
  const [open, setOpen] = React.useState<RevisionFull | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [view, setView] = React.useState<"changes" | "before">("changes");

  React.useEffect(() => {
    let alive = true;
    setRevisions(null);
    setOpen(null);
    readRevisions(note.id)
      .then((found) => alive && setRevisions(found))
      .catch(() => alive && setRevisions([]));
    return () => {
      alive = false;
    };
  }, [note.id, note.version]);

  if (revisions === null) return <Skeleton rows={3} />;
  if (revisions.length === 0) return <p className="mn-panel-empty">{t("panel.no_history")}</p>;

  if (open) {
    return (
      <div className="mn-revision">
        <button type="button" className="mn-revision-back" onClick={() => setOpen(null)}>
          <Icon name="chevron-left" />
          {t("panel.history")}
        </button>
        <p className="mn-revision-when">
          {t(
            open.replaced_by === "tool"
              ? "history.before_claude"
              : open.replaced_by === "import"
                ? open.replaced_app
                  ? "history.before_app"
                  : "history.before_import"
                : "history.before_you",
            { app: open.replaced_app ?? "", when: ago(open.replaced_at) },
          )}
        </p>
        <Button
          variant="tinted"
          icon="undo"
          block
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onRestore(open);
              setOpen(null);
            } finally {
              setBusy(false);
            }
          }}
        >
          {t("history.restore")}
        </Button>
        <SegmentedControl
          label={t("history.view")}
          options={[
            { value: "changes" as const, label: t("history.changes") },
            { value: "before" as const, label: t("history.before") },
          ]}
          value={view}
          onChange={setView}
        />
        {view === "before" ? (
          <div className="mn-prose mn-revision-body" dangerouslySetInnerHTML={{ __html: render(open.content) }} />
        ) : (
          <Changes before={open.content} after={note.content} />
        )}
      </div>
    );
  }

  return (
    <ul className="mn-history">
      {revisions.map((revision) => (
        <li key={revision.id}>
          <button
            type="button"
            className="mn-history-row"
            data-claude={revision.replaced_by === "tool" || undefined}
            onClick={() => void readRevision(note.id, revision.id).then(setOpen)}
          >
            <span className="mn-history-who">
              {revision.replaced_by === "tool"
                ? t("history.by_claude")
                : revision.replaced_by === "import"
                  ? revision.replaced_app
                    ? t("history.by_app", { app: revision.replaced_app })
                    : t("history.by_import")
                  : t("history.by_you")}
            </span>
            <span className="mn-history-when">{ago(revision.replaced_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Changes({ before, after }: { before: string; after: string }) {
  const lines = hunks(diff(before, after));
  if (lines.every((line) => line === null || line.op === "same")) {
    return <p className="mn-panel-empty">{t("history.same")}</p>;
  }
  return (
    <pre className="mn-diff" aria-label={t("history.diff")}>
      {lines.map((line, index) =>
        line === null ? (
          <span key={index} className="mn-diff-gap">
            …
          </span>
        ) : (
          <span key={index} className="mn-diff-line" data-op={line.op}>
            {line.op === "add" ? "+ " : line.op === "remove" ? "− " : "  "}
            {line.text || " "}
          </span>
        ),
      )}
    </pre>
  );
}

function LocalGraph({ note, links, onOpen }: { note: Note; links: Links | null; onOpen: (id: string) => void }) {
  const [depth, setDepth] = React.useState<"1" | "2">("1");
  const [graph, setGraph] = React.useState<Graph | null | undefined>(undefined);
  React.useEffect(() => {
    let alive = true;
    setGraph(undefined);
    readGraph(note.id, Number(depth))
      .then((found) => alive && setGraph(found))
      .catch(() => alive && setGraph(null));
    return () => {
      alive = false;
    };
  }, [note.id, depth, links]);
  return (
    <div className="mn-local-graph">
      <SegmentedControl
        label={t("panel.hops")}
        options={[
          { value: "1" as const, label: t("panel.neighbours") },
          { value: "2" as const, label: t("panel.theirs") },
        ]}
        value={depth}
        onChange={setDepth}
      />
      {graph === undefined ? (
        <Skeleton rows={3} />
      ) : graph && graph.nodes.length > 1 ? (
        <GraphView graph={graph} focus={note.id} onOpen={(id) => id !== note.id && onOpen(id)} compact />
      ) : (
        <p className="mn-panel-empty">{t("panel.alone")}</p>
      )}
    </div>
  );
}
