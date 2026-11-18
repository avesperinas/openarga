export const MAX_CHARS = 5_000_000;
export const SHOWN = 5;

export type StatementFormat = "csv" | "ofx";

export interface FilePreviewData {
  header: string[] | null;
  rows: string[][];
  total: number;
}

export function formatOf(name: string, text: string): StatementFormat {
  if (/\.(ofx|qfx)$/i.test(name) || /<OFX>/i.test(text)) return "ofx";
  return "csv";
}

function delimiterOf(head: string): string {
  return [";", ",", "\t", "|"].reduce((best, one) => (head.split(one).length > head.split(best).length ? one : best), ",");
}

export function splitRow(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let at = 0; at < line.length; at += 1) {
    const char = line[at];
    if (quoted) {
      if (char === '"' && line[at + 1] === '"') {
        cell += '"';
        at += 1;
      } else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"') quoted = true;
    else if (char === delimiter) {
      cells.push(cell.trim());
      cell = "";
    } else cell += char;
  }
  cells.push(cell.trim());
  return cells;
}

function csvPreview(text: string, limit: number): FilePreviewData {
  const lines = text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0);
  const [head, ...body] = lines;
  if (head === undefined) return { header: null, rows: [], total: 0 };
  const delimiter = delimiterOf(head);
  return { header: splitRow(head, delimiter), rows: body.slice(0, limit).map((line) => splitRow(line, delimiter)), total: body.length };
}

function tag(block: string, name: string): string {
  const found = new RegExp(`<${name}>([^<\\r\\n]*)`, "i").exec(block);
  return found?.[1]?.trim() ?? "";
}

function ofxDay(raw: string): string {
  return /^\d{8}/.test(raw) ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` : raw;
}

function ofxPreview(text: string, limit: number): FilePreviewData {
  const blocks = text.split(/<STMTTRN>/i).slice(1);
  const rows = blocks.slice(0, limit).map((block) => {
    const name = tag(block, "NAME");
    const memo = tag(block, "MEMO");
    return [ofxDay(tag(block, "DTPOSTED")), tag(block, "TRNAMT"), [name, memo].filter(Boolean).join(" ")];
  });
  return { header: null, rows, total: blocks.length };
}

export function previewOf(text: string, format: StatementFormat, limit = SHOWN): FilePreviewData {
  return format === "ofx" ? ofxPreview(text, limit) : csvPreview(text, limit);
}
