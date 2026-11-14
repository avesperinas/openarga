import { EmptyState, OfflineNotice, SearchField, Switch } from "@openarga/ui";
import * as React from "react";

import { readGraph } from "./api";
import { GraphView } from "./Lazy";
import { Pending, useLoad } from "./Loads";
import { fold } from "./tree";
import { t } from "./lang";

export function GraphScreen({ onOpen, onNewNote }: { onOpen: (id: string) => void; onNewNote: () => void }) {
  const { data: graph, found } = useLoad("graph", () => readGraph());
  const [query, setQuery] = React.useState("");
  const [orphans, setOrphans] = React.useState(false);

  const shown = React.useMemo(() => {
    if (!graph || orphans) return graph;
    return { ...graph, nodes: graph.nodes.filter((n) => n.links > 0) };
  }, [graph, orphans]);

  const words = fold(query.trim());
  const highlight = React.useMemo(
    () => (words ? (n: { title: string; folder: string }) => fold(`${n.folder}/${n.title}`).includes(words) : undefined),
    [words],
  );

  if (!graph) return <Pending found={found} />;
  if (graph.nodes.length === 0) {
    return (
      <EmptyState icon="graph" title={t("graph.empty")} action={{ label: t("action.new_note"), icon: "plus", onClick: onNewNote }}>
        {t("graph.empty_detail")}
      </EmptyState>
    );
  }

  return (
    <div className="mn-graph-screen">
      <OfflineNotice />
      <div className="mn-graph-tools">
        <SearchField value={query} onChange={setQuery} placeholder={t("graph.highlight_placeholder")} label={t("graph.highlight")} />
        <div className="mn-switch-row">
          <span>{t("graph.orphans")}</span>
          <Switch label={t("graph.show_orphans")} checked={orphans} onChange={setOrphans} />
        </div>
      </div>
      <GraphView graph={shown!} onOpen={onOpen} highlight={highlight} />
      <p className="mn-graph-legend">
        {t("graph.hint", { notes: shown!.nodes.length, links: graph.edges.length })}
      </p>
    </div>
  );
}
