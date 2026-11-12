import { EmptyState, OfflineNotice, SearchField, Skeleton } from "@openarga/ui";
import * as React from "react";

import { type NoteSummary, readTags, search } from "./api";
import { Pending, useLoad } from "./Loads";

interface Props {
  query: string;
  tag: string;
  onQuery: (query: string, tag: string) => void;
  onOpen: (note: NoteSummary) => void;
}

export function SearchScreen({ query, tag, onQuery, onOpen }: Props) {
  const [draft, setDraft] = React.useState(query);
  const asked = query.trim() || tag;
  const tags = useLoad("tags", readTags, { persist: true });
  const found = useLoad(asked ? `search:${query.trim()}#${tag}` : null, () =>
    search({ q: query.trim() || undefined, tag: tag || undefined }),
  );
  const hits = asked ? found.data : null;

  React.useEffect(() => setDraft(query), [query]);

  React.useEffect(() => {
    if (draft === query) return;
    const timer = setTimeout(() => onQuery(draft, tag), 250);
    return () => clearTimeout(timer);
  }, [draft, query, tag, onQuery]);

  return (
    <div className="mn-search">
      <OfflineNotice />
      <SearchField value={draft} onChange={setDraft} placeholder="Palabras, sin acentos si quieres" label="Buscar en las notas" />
      {tag && (
        <div className="mn-search-filter">
          <span className="mn-tag">#{tag}</span>
          <button type="button" className="mn-search-clear" onClick={() => onQuery(draft, "")}>
            Quitar
          </button>
        </div>
      )}
      {asked && hits === null ? (
        <Pending found={found.found} rows={4} />
      ) : hits === null ? (
        tags.data === null ? (
          tags.found.error ? null : <Skeleton rows={2} />
        ) : tags.data.length > 0 ? (
          <div className="mn-tag-cloud" aria-label="Tags">
            {tags.data.map((one) => (
              <button key={one.tag} type="button" className="mn-tag" onClick={() => onQuery(draft, one.tag)}>
                #{one.tag}
                <span className="mn-tag-count">{one.notes}</span>
              </button>
            ))}
          </div>
        ) : null
      ) : hits.length === 0 ? (
        <EmptyState icon="search" title="Nada con eso" action={{ label: "Borrar la búsqueda", onClick: () => onQuery("", "") }}>
          Prueba con menos palabras o con el principio de una.
        </EmptyState>
      ) : (
        <ul className="mn-hits">
          {hits.map((hit) => (
            <li key={hit.id}>
              <button type="button" className="mn-hit" onClick={() => onOpen(hit)}>
                <span className="mn-hit-title">{hit.title}</span>
                {(hit.source || hit.folder) && (
                  <span className="mn-hit-path">{hit.source ? `${hit.source.name} · ${hit.folder}` : hit.folder}</span>
                )}
                {hit.snippet && <span className="mn-hit-snippet">{hit.snippet}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
