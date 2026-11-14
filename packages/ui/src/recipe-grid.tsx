"use client";

import * as React from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./controls";
import { say } from "./words";

export interface RecipeGridRow {
  id: string | number;
  label: string;
  amount?: string;
  unused?: boolean;
}

export interface RecipeGridCell {
  id: string | number;
  label: string;
  detail?: string;
  note?: string;
  column: number;
  row: number;
  span: number;
  attended?: boolean;
}

export interface RecipeGridBand {
  id: string | number;
  label: string;
  note?: string;
}

export interface RecipeGridProps {
  label: string;
  rows: RecipeGridRow[];
  cells: RecipeGridCell[];
  bands?: RecipeGridBand[];
  columns: number;
}

export const ZOOM = [0.8, 1, 1.3, 1.7, 2.2] as const;

export function zoomStep(scale: number, direction: 1 | -1): number {
  const at = ZOOM.indexOf(scale as (typeof ZOOM)[number]);
  const next = (at === -1 ? 1 : at) + direction;
  return ZOOM[Math.min(Math.max(next, 0), ZOOM.length - 1)] ?? 1;
}

export function layout(
  rows: RecipeGridRow[],
  cells: RecipeGridCell[],
  columns: number,
): RecipeGridCell[][] {
  const pending = new Array(columns + 1).fill(0);
  return rows.map((_, index) => {
    const starting = cells
      .filter((cell) => cell.row === index + 1)
      .sort((a, b) => a.column - b.column);
    const line: RecipeGridCell[] = [];
    for (let column = 1; column <= columns; column += 1) {
      if (pending[column] > 0) {
        pending[column] -= 1;
        continue;
      }
      const here = starting.find((cell) => cell.column === column);
      if (here) {
        line.push(here);
        pending[column] = here.span - 1;
      } else {
        line.push({ id: `hueco-${index}-${column}`, label: "", column, row: index + 1, span: 1 });
      }
    }
    return line;
  });
}

function Table({ label, rows, cells, bands = [], columns }: RecipeGridProps) {
  const lines = layout(rows, cells, columns);
  return (
    <table className="recipe-grid-table">
      <caption className="recipe-grid-said">{label}</caption>
      <tbody>
        {bands.map((band) => (
          <tr key={band.id} className="recipe-grid-band-row">
            <td className="recipe-grid-band" colSpan={columns + 1}>
              <span className="recipe-grid-verb">{band.label}</span>
              {band.note && <span className="recipe-grid-note">{band.note}</span>}
            </td>
          </tr>
        ))}
        {rows.map((row, index) => (
          <tr key={row.id}>
            <th
              className="recipe-grid-ingredient"
              scope="row"
              data-unused={row.unused ? true : undefined}
            >
              {row.amount && <span className="recipe-grid-amount">{row.amount}</span>}
              <span className="recipe-grid-name">{row.label}</span>
            </th>
            {(lines[index] ?? []).map((cell) =>
              cell.label ? (
                <td
                  key={cell.id}
                  className="recipe-grid-step"
                  rowSpan={cell.span}
                  data-attended={cell.attended === false ? undefined : true}
                >
                  <span className="recipe-grid-verb">{cell.label}</span>
                  {cell.detail && <span className="recipe-grid-text">{cell.detail}</span>}
                  {cell.note && <span className="recipe-grid-note">{cell.note}</span>}
                </td>
              ) : (
                <td key={cell.id} className="recipe-grid-gap" />
              ),
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const useBrowserLayoutEffect = typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;

export function RecipeGrid(props: RecipeGridProps) {
  const [scale, setScale] = React.useState(1);
  const [full, setFull] = React.useState(false);
  const [host, setHost] = React.useState<HTMLElement | null>(null);
  useBrowserLayoutEffect(() => setHost(document.body), []);

  React.useEffect(() => {
    if (!full) return;
    const escape = (event: KeyboardEvent) => event.key === "Escape" && setFull(false);
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [full]);

  if (props.rows.length === 0) return null;

  const controls = (
    <div className="recipe-grid-controls">
      <IconButton
        icon="minus"
        label={say("grid.smaller")}
        size="small"
        disabled={scale === ZOOM[0]}
        onClick={() => setScale(zoomStep(scale, -1))}
      />
      <IconButton
        icon="plus"
        label={say("grid.bigger")}
        size="small"
        disabled={scale === ZOOM[ZOOM.length - 1]}
        onClick={() => setScale(zoomStep(scale, 1))}
      />
      <IconButton
        icon={full ? "close" : "expand"}
        label={full ? say("grid.close") : say("grid.full_screen")}
        size="small"
        onClick={() => setFull(!full)}
      />
    </div>
  );

  const stage = (
    <div className="recipe-grid" data-full={full ? true : undefined}>
      {controls}
      <div
        className="recipe-grid-scroller"
        style={{ "--grid-scale": scale } as React.CSSProperties}
        tabIndex={0}
        role="group"
        aria-label={props.label}
      >
        <Table {...props} />
      </div>
    </div>
  );

  return full && host ? createPortal(stage, host) : stage;
}
