import { EmptyState, OfflineNotice, SearchField, Switch } from "@openarga/ui";
import * as React from "react";

import { readGraph } from "./api";
import { GraphView } from "./Lazy";
import { Pending, useLoad } from "./Loads";
import { fold } from "./tree";

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
      <EmptyState icon="graph" title="Aún no hay nada que enlazar" action={{ label: "Nota nueva", icon: "plus", onClick: onNewNote }}>
        El grafo aparece cuando las notas se enlazan entre sí con [[…]].
      </EmptyState>
    );
  }

  return (
    <div className="mn-graph-screen">
      <OfflineNotice />
      <div className="mn-graph-tools">
        <SearchField value={query} onChange={setQuery} placeholder="Resaltar por título o carpeta" label="Resaltar" />
        <div className="mn-switch-row">
          <span>Notas sin enlaces</span>
          <Switch label="Enseñar las notas sin enlaces" checked={orphans} onChange={setOrphans} />
        </div>
      </div>
      <GraphView graph={shown!} onOpen={onOpen} highlight={highlight} />
      <p className="mn-graph-legend">
        {shown!.nodes.length} notas · {graph.edges.length} enlaces. Arrastra para moverte, rueda o dos dedos para acercarte.
      </p>
    </div>
  );
}
