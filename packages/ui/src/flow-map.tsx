"use client";

import * as React from "react";

import { SERIES_COLORS } from "./analysis";

export interface MapNode {
  id: string;
  name: string;
  kind: string;
  group: string;
  group_name: string;
  inflow: number;
  outflow: number;
  column?: number;
}

export interface MapLink {
  source: string;
  target: string;
  value: number;
}

export interface FlowMapProps {
  label: string;
  nodes: MapNode[];
  links: MapLink[];
  format?: (value: number) => string;
  onSelect?: (pick: { link: MapLink } | { node: MapNode }) => void;
}

const FRINGE = new Set(["income", "expense", "elsewhere"]);
const BOX_W = 150;
const BOX_H = 58;
const COL_W = 230;
const GAP = 34;
const PAD = 24;
const LANE = 26;

export interface Placed extends MapNode {
  column: number;
  x: number;
  y: number;
}

export function placeBoxes(nodes: MapNode[], links: MapLink[]): { placed: Placed[]; width: number; height: number } {
  const source = (one: MapNode) => one.inflow === 0 && (FRINGE.has(one.kind) || one.kind === "person");
  const sink = (one: MapNode) => one.outflow === 0 && FRINGE.has(one.kind);
  const middle = nodes.filter((one) => !source(one) && !sink(one));
  const depth = new Map(middle.map((one) => [one.id, 0]));
  for (let round = 0; round < middle.length; round++) {
    let changed = false;
    for (const link of links) {
      const from = depth.get(link.source);
      const to = depth.get(link.target);
      if (from === undefined || to === undefined) continue;
      if (to < from + 1 && from + 1 <= middle.length) {
        depth.set(link.target, from + 1);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const hasSources = nodes.some(source);
  const offset = hasSources ? 1 : 0;
  const deepest = Math.max(0, ...depth.values());
  const last = offset + (middle.length ? deepest + 1 : 0);
  const before = (one: MapNode) => {
    const targets = links
      .filter((link) => link.source === one.id)
      .map((link) => depth.get(link.target))
      .filter((value): value is number => value !== undefined);
    return targets.length ? Math.max(0, offset + Math.min(...targets) - 1) : 0;
  };
  const given = nodes.length > 0 && nodes.every((one) => one.column !== undefined);
  const columns = new Map<number, MapNode[]>();
  for (const one of nodes) {
    const column = given
      ? (one.column ?? 0)
      : source(one)
        ? before(one)
        : sink(one)
          ? last
          : offset + (depth.get(one.id) ?? 0);
    columns.set(column, [...(columns.get(column) ?? []), one]);
  }
  const through = (one: MapNode) => Math.max(one.inflow, one.outflow);
  const groupWeight = new Map<string, number>();
  for (const one of nodes) groupWeight.set(one.group, (groupWeight.get(one.group) ?? 0) + through(one));
  const tallest = Math.max(0, ...[...columns.values()].map((list) => list.length));
  const height = PAD * 2 + tallest * BOX_H + Math.max(0, tallest - 1) * GAP;
  const placed: Placed[] = [];
  for (const [column, list] of columns) {
    const sorted = [...list].sort(
      (a, b) =>
        (given ? (groupWeight.get(b.group) ?? 0) - (groupWeight.get(a.group) ?? 0) : 0) ||
        (given ? a.group.localeCompare(b.group) : 0) ||
        through(b) - through(a),
    );
    const used = sorted.length * BOX_H + Math.max(0, sorted.length - 1) * GAP;
    const top = (height - used) / 2;
    sorted.forEach((one, index) => {
      placed.push({ ...one, column, x: PAD + column * COL_W, y: top + index * (BOX_H + GAP) });
    });
  }
  const lastColumn = given ? Math.max(0, ...columns.keys()) : last;
  const width = PAD * 2 + lastColumn * COL_W + BOX_W;
  return { placed, width, height };
}

export function groupColours(nodes: MapNode[]): Map<string, string> {
  const moved = new Map<string, number>();
  for (const one of nodes) {
    if (FRINGE.has(one.kind)) continue;
    moved.set(one.group, (moved.get(one.group) ?? 0) + Math.max(one.inflow, one.outflow));
  }
  const ranked = [...moved.entries()].sort((a, b) => b[1] - a[1]).map(([group]) => group);
  return new Map(ranked.map((group, index) => [group, index < SERIES_COLORS ? String(index) : "others"]));
}

function shorten(text: string, room = 19): string {
  return text.length > room ? `${text.slice(0, room - 1)}…` : text;
}

export function FlowMap({
  label,
  nodes,
  links,
  format = (value) => value.toLocaleString("es-ES"),
  onSelect,
}: FlowMapProps) {
  const [focus, setFocus] = React.useState<string | null>(null);
  const press = (pick: { link: MapLink } | { node: MapNode }) => (event: React.KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect?.(pick);
    }
  };
  if (nodes.length === 0 || links.length === 0) return <p className="widget-note">Sin movimientos en este tramo</p>;
  const { placed, width, height: boxes } = placeBoxes(nodes, links);
  const at = new Map(placed.map((one) => [one.id, one]));
  const colours = groupColours(nodes);
  const colour = (one: MapNode) => (FRINGE.has(one.kind) ? undefined : colours.get(one.group));
  const heaviest = Math.max(...links.map((one) => one.value));
  const thickness = (value: number) => 1.5 + 7 * Math.sqrt(value / heaviest);
  const groups = [...new Map(nodes.filter((one) => !FRINGE.has(one.kind)).map((one) => [one.group, one])).values()];
  const names = new Map(nodes.map((one) => [one.id, one.name]));
  const long = links
    .filter((link) => {
      const from = at.get(link.source);
      const to = at.get(link.target);
      return from && to && to.column - from.column !== 1 && to.column !== from.column;
    })
    .sort((a, b) => b.value - a.value);
  const lane = new Map(long.map((link, index) => [`${link.source}-${link.target}`, index]));
  const height = boxes + (long.length ? long.length * LANE + PAD / 2 : 0);

  return (
    <figure className="flow-map" aria-label={label}>
      <div className="flow-map-scroll">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={label}
          style={{ minWidth: `${Math.min(width, 900) / 16}rem` }}
        >
          {links.map((link) => {
            const from = at.get(link.source);
            const to = at.get(link.target);
            if (!from || !to) return null;
            const stroke = thickness(link.value);
            const dim = focus !== null && focus !== link.source && focus !== link.target;
            let path: string;
            let head: string;
            let middle: [number, number];
            const track = lane.get(`${link.source}-${link.target}`);
            if (to.column === from.column) {
              const sx = from.x + BOX_W;
              const sy = from.y + BOX_H / 2 + 8;
              const tx = to.x + BOX_W + 6;
              const ty = to.y + BOX_H / 2 - 8;
              const bulge = sx + 22 + Math.min(40, Math.abs(ty - sy) / 8);
              path = `M ${sx} ${sy} C ${bulge} ${sy}, ${bulge} ${ty}, ${tx} ${ty}`;
              head = `${tx + 2} ${ty - 5 - stroke / 2}, ${tx - 6} ${ty}, ${tx + 2} ${ty + 5 + stroke / 2}`;
              middle = [bulge - 4, (sy + ty) / 2 + 4];
            } else if (track !== undefined) {
              const sx = from.x + BOX_W;
              const sy = from.y + BOX_H / 2;
              const tx = to.x - 6;
              const ty = to.y + BOX_H / 2;
              const nudge = (track % 3) * 8;
              const out = sx + 18 + nudge;
              const back = to.x - 22 - nudge;
              const y = boxes + PAD / 4 + track * LANE;
              path = `M ${sx} ${sy} H ${out} V ${y} H ${back} V ${ty} H ${tx}`;
              head = `${tx - 2} ${ty - 5 - stroke / 2}, ${tx + 6} ${ty}, ${tx - 2} ${ty + 5 + stroke / 2}`;
              middle = [(out + back) / 2, y];
            } else {
              const sx = from.x + BOX_W;
              const sy = from.y + BOX_H / 2;
              const tx = to.x - 6;
              const ty = to.y + BOX_H / 2;
              const bend = (tx - sx) / 2;
              path = `M ${sx} ${sy} C ${sx + bend} ${sy}, ${tx - bend} ${ty}, ${tx} ${ty}`;
              head = `${tx - 2} ${ty - 5 - stroke / 2}, ${tx + 6} ${ty}, ${tx - 2} ${ty + 5 + stroke / 2}`;
              middle = [(sx + tx) / 2, (sy + ty) / 2];
            }
            return (
              <g
                key={`${link.source}-${link.target}`}
                className="flow-map-link"
                data-series={colour(from)}
                data-fringe={colour(from) === undefined ? "" : undefined}
                data-dim={dim ? "" : undefined}
                data-clickable={onSelect ? "" : undefined}
                role={onSelect ? "button" : undefined}
                tabIndex={onSelect ? 0 : undefined}
                aria-label={
                  onSelect ? `${names.get(link.source)} → ${names.get(link.target)}: ${format(link.value)}` : undefined
                }
                onClick={onSelect ? () => onSelect({ link }) : undefined}
                onKeyDown={onSelect ? press({ link }) : undefined}
              >
                <title>{`${names.get(link.source)} → ${names.get(link.target)}: ${format(link.value)}`}</title>
                <path d={path} style={{ strokeWidth: stroke }} />
                <polygon points={head} />
                <text x={middle[0]} y={middle[1] - 4} textAnchor="middle">
                  {format(link.value)}
                </text>
              </g>
            );
          })}
          {placed.map((one) => (
            <g
              key={one.id}
              className="flow-map-box"
              data-series={colour(one)}
              data-fringe={colour(one) === undefined ? "" : undefined}
              tabIndex={0}
              data-clickable={onSelect ? "" : undefined}
              role={onSelect ? "button" : undefined}
              aria-label={onSelect ? one.name : undefined}
              onClick={onSelect ? () => onSelect({ node: one }) : undefined}
              onKeyDown={onSelect ? press({ node: one }) : undefined}
              onMouseEnter={() => setFocus(one.id)}
              onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(one.id)}
              onBlur={() => setFocus(null)}
            >
              <title>{`${one.name}: entra ${format(one.inflow)}, sale ${format(one.outflow)}`}</title>
              <rect x={one.x} y={one.y} width={BOX_W} height={BOX_H} rx="12" />
              <text className="flow-map-name" x={one.x + 12} y={one.y + 23}>
                {shorten(one.name)}
              </text>
              <text className="flow-map-sums" x={one.x + 12} y={one.y + 42}>
                {[one.inflow ? `+${format(one.inflow)}` : null, one.outflow ? `−${format(one.outflow)}` : null]
                  .filter(Boolean)
                  .join("  ")}
              </text>
            </g>
          ))}
        </svg>
      </div>
      {groups.length > 1 && (
        <ul className="series-chart-legend">
          {groups.map((one) => (
            <li key={one.group}>
              <span className="series-chart-swatch" data-series={colours.get(one.group)} aria-hidden="true" />
              {one.group_name}
            </li>
          ))}
        </ul>
      )}
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
              {links.map((link) => (
                <tr key={`${link.source}-${link.target}`}>
                  <th scope="row">{names.get(link.source)}</th>
                  <th scope="row">{names.get(link.target)}</th>
                  <td>{format(link.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
