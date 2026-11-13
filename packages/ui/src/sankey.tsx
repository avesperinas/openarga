"use client";

import * as React from "react";
import { locale } from "./regional";

export interface FlowNode {
  id: string;
  name: string;
  column: number;
  kind: "income" | "you" | "member" | "common" | "account" | "expense" | "saving" | "deficit";
}

export interface FlowLink {
  source: string;
  target: string;
  value: number;
}

export interface SankeyProps {
  nodes: FlowNode[];
  links: FlowLink[];
  label: string;
  format?: (value: number) => string;
  rowHeight?: number;
  vertical?: boolean;
  share?: (node: FlowNode, value: number) => string;
}

const WIDTH = 720;
const ROW = 44;
const NODE = 12;
const GAP = 14;
const LABEL_ROOM = 220;

export interface Placed extends FlowNode {
  x: number;
  y: number;
  height: number;
  value: number;
}

export interface Band {
  source: Placed;
  target: Placed;
  value: number;
  from: number;
  to: number;
  width: number;
}

export function layout(
  nodes: FlowNode[],
  links: FlowLink[],
  rowHeight = ROW,
): { placed: Placed[]; bands: Band[]; height: number } {
  const valueIn = new Map<string, number>();
  const valueOut = new Map<string, number>();
  for (const link of links) {
    valueOut.set(link.source, (valueOut.get(link.source) ?? 0) + link.value);
    valueIn.set(link.target, (valueIn.get(link.target) ?? 0) + link.value);
  }
  const columns = [...new Set(nodes.map((node) => node.column))].sort((a, b) => a - b);
  const byColumn = columns.map((column) => nodes.filter((node) => node.column === column));
  const valueOf = (node: FlowNode) => Math.max(valueIn.get(node.id) ?? 0, valueOut.get(node.id) ?? 0);
  const crowded = Math.max(1, ...byColumn.map((one) => one.length));
  const height = Math.max(240, crowded * rowHeight);
  const scale = Math.min(
    ...byColumn.map((one) => {
      const total = one.reduce((sum, node) => sum + valueOf(node), 0);
      return total > 0 ? (height - GAP * (one.length - 1)) / total : Number.POSITIVE_INFINITY;
    }),
  );
  const k = Number.isFinite(scale) ? scale : 1;
  const span = WIDTH - LABEL_ROOM - NODE;
  const placed: Placed[] = [];
  const rank = new Map<string, number>();
  const parentOf = (node: FlowNode): number => {
    let best: FlowLink | null = null;
    for (const link of links) {
      if (link.target === node.id && rank.has(link.source) && (!best || link.value > best.value)) best = link;
    }
    return best ? rank.get(best.source)! : -1;
  };
  byColumn.forEach((column, index) => {
    const x = columns.length === 1 ? 0 : (index / (columns.length - 1)) * span;
    const parents = new Map(column.map((node) => [node.id, parentOf(node)]));
    const ordered = [...column].sort(
      (a, b) => parents.get(a.id)! - parents.get(b.id)! || valueOf(b) - valueOf(a),
    );
    ordered.forEach((node, position) => rank.set(node.id, index * 1000 + position));
    const used = ordered.reduce((sum, node) => sum + valueOf(node) * k, 0) + GAP * (ordered.length - 1);
    let y = (height - used) / 2;
    for (const node of ordered) {
      const size = Math.max(1, valueOf(node) * k);
      placed.push({ ...node, x, y, height: size, value: valueOf(node) });
      y += size + GAP;
    }
  });
  const at = new Map(placed.map((node) => [node.id, node]));
  const outUsed = new Map<string, number>();
  const inUsed = new Map<string, number>();
  const bands: Band[] = [];
  const sorted = links
    .filter((link) => at.has(link.source) && at.has(link.target) && link.value > 0)
    .sort((a, b) => at.get(a.source)!.y - at.get(b.source)!.y || at.get(a.target)!.y - at.get(b.target)!.y);
  for (const link of sorted) {
    const source = at.get(link.source)!;
    const target = at.get(link.target)!;
    const width = Math.max(1, link.value * k);
    const out = outUsed.get(source.id) ?? 0;
    const into = inUsed.get(target.id) ?? 0;
    outUsed.set(source.id, out + width);
    inUsed.set(target.id, into + width);
    bands.push({ source, target, value: link.value, from: source.y + out + width / 2, to: target.y + into + width / 2, width });
  }
  return { placed, bands, height };
}

export function Sankey({
  nodes,
  links,
  label,
  format = (value) => value.toLocaleString(locale()),
  rowHeight = ROW,
  vertical = false,
  share,
}: SankeyProps) {
  const [focus, setFocus] = React.useState<string | null>(null);
  if (links.length === 0) return <p className="widget-note">Sin movimientos en este rango</p>;
  const { placed, bands, height } = layout(nodes, links, rowHeight);
  const touches = (band: Band) => focus === null || band.source.id === focus || band.target.id === focus;
  if (vertical) {
    return (
      <VerticalSankey
        placed={placed}
        bands={bands}
        across={height}
        label={label}
        format={format}
        share={share}
        focus={focus}
        onFocus={setFocus}
        touches={touches}
      />
    );
  }

  return (
    <figure className="sankey" aria-label={label}>
      <div className="sankey-scroll">
        <svg viewBox={`-4 -8 ${WIDTH + 8} ${height + 16}`} role="img" aria-label={label}>
          {bands.map((band) => {
            const x0 = band.source.x + NODE;
            const x1 = band.target.x;
            const middle = (x0 + x1) / 2;
            return (
              <path
                key={`${band.source.id}>${band.target.id}`}
                className="sankey-band"
                data-kind={band.source.kind}
                data-dim={!touches(band) || undefined}
                d={`M ${x0} ${band.from} C ${middle} ${band.from}, ${middle} ${band.to}, ${x1} ${band.to}`}
                strokeWidth={band.width}
              >
                <title>{`${band.source.name} → ${band.target.name}: ${format(band.value)}`}</title>
              </path>
            );
          })}
          {placed.map((node) => (
            <g
              key={node.id}
              className="sankey-node"
              data-kind={node.kind}
              tabIndex={0}
              onMouseEnter={() => setFocus(node.id)}
              onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(node.id)}
              onBlur={() => setFocus(null)}
            >
              <rect x={node.x} y={node.y} width={NODE} height={node.height} rx="3" />
              <text x={node.x + NODE + 6} y={node.y + node.height / 2} dominantBaseline="middle">
                <tspan className="sankey-name">{node.name}</tspan>
                <tspan className="sankey-value" dx="6">
                  {format(node.value)}
                </tspan>
              </text>
              <title>{`${node.name}: ${format(node.value)}`}</title>
            </g>
          ))}
        </svg>
      </div>
      <details className="series-chart-table">
        <summary>Ver como tabla</summary>
        <div className="series-chart-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">De</th>
                <th scope="col">A</th>
                <th scope="col">Importe</th>
              </tr>
            </thead>
            <tbody>
              {bands.map((band) => (
                <tr key={`${band.source.id}>${band.target.id}`}>
                  <th scope="row">{band.source.name}</th>
                  <td>{band.target.name}</td>
                  <td>{format(band.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function VerticalSankey({
  placed,
  bands,
  across,
  label,
  format,
  share,
  focus,
  onFocus,
  touches,
}: {
  placed: Placed[];
  bands: Band[];
  across: number;
  label: string;
  format: (value: number) => string;
  share?: (node: FlowNode, value: number) => string;
  focus: string | null;
  onFocus: (id: string | null) => void;
  touches: (band: Band) => boolean;
}) {
  const columns = [...new Set(placed.map((node) => node.x))].sort((a, b) => a - b);
  const span = WIDTH - LABEL_ROOM - NODE;
  const along = Math.max(1, columns.length - 1) * Math.min(160, across / 2.2);
  const at = (x: number) => (span > 0 ? (x / span) * along : 0);
  const down = along + NODE;
  const lit = (node: Placed) =>
    focus === null || node.id === focus || bands.some((band) => touches(band) && (band.source.id === node.id || band.target.id === node.id));
  return (
    <figure className="sankey" data-vertical="" aria-label={label}>
      <svg viewBox={`-4 -4 ${across + 8} ${down + 8}`} role="img" aria-label={label} className="sankey-vertical">
        {bands.map((band) => {
          const y0 = at(band.source.x) + NODE;
          const y1 = at(band.target.x);
          const middle = (y0 + y1) / 2;
          return (
            <path
              key={`${band.source.id}>${band.target.id}`}
              className="sankey-band"
              data-kind={band.source.kind}
              data-dim={!touches(band) || undefined}
              d={`M ${band.from} ${y0} C ${band.from} ${middle}, ${band.to} ${middle}, ${band.to} ${y1}`}
              strokeWidth={band.width}
            >
              <title>{`${band.source.name} → ${band.target.name}: ${format(band.value)}`}</title>
            </path>
          );
        })}
        {placed.map((node) => (
          <g key={node.id} className="sankey-node" data-kind={node.kind} data-dim={!lit(node) || undefined}>
            <rect x={node.y} y={at(node.x)} width={node.height} height={NODE} rx="3" />
            <title>{`${node.name}: ${format(node.value)}`}</title>
          </g>
        ))}
      </svg>
      <div className="sankey-legend">
        {columns.map((x) => (
          <ul key={x} className="sankey-legend-column">
            {placed
              .filter((node) => node.x === x)
              .sort((a, b) => b.value - a.value)
              .map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    className="sankey-legend-item"
                    data-kind={node.kind}
                    aria-pressed={focus === node.id}
                    onClick={() => onFocus(focus === node.id ? null : node.id)}
                  >
                    <span className="sankey-legend-dot" aria-hidden="true" />
                    <span className="sankey-legend-name">{node.name}</span>
                    <span className="sankey-legend-value">
                      {format(node.value)}
                      {share ? ` · ${share(node, node.value)}` : ""}
                    </span>
                  </button>
                </li>
              ))}
          </ul>
        ))}
      </div>
      <details className="series-chart-table">
        <summary>Ver como tabla</summary>
        <div className="series-chart-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">De</th>
                <th scope="col">A</th>
                <th scope="col">Importe</th>
              </tr>
            </thead>
            <tbody>
              {bands.map((band) => (
                <tr key={`${band.source.id}>${band.target.id}`}>
                  <th scope="row">{band.source.name}</th>
                  <td>{band.target.name}</td>
                  <td>{format(band.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
