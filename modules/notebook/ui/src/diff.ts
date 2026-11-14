export type DiffLine = { op: "same" | "add" | "remove"; text: string };

export function diff(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head += 1;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail += 1;
  const x = a.slice(head, a.length - tail);
  const y = b.slice(head, b.length - tail);
  const table: number[][] = Array.from({ length: x.length + 1 }, () => new Array<number>(y.length + 1).fill(0));
  for (let i = x.length - 1; i >= 0; i -= 1) {
    for (let j = y.length - 1; j >= 0; j -= 1) {
      table[i]![j] = x[i] === y[j] ? table[i + 1]![j + 1]! + 1 : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }
  const middle: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) {
      middle.push({ op: "same", text: x[i]! });
      i += 1;
      j += 1;
    } else if (table[i + 1]![j]! >= table[i]![j + 1]!) {
      middle.push({ op: "remove", text: x[i]! });
      i += 1;
    } else {
      middle.push({ op: "add", text: y[j]! });
      j += 1;
    }
  }
  while (i < x.length) middle.push({ op: "remove", text: x[i++]! });
  while (j < y.length) middle.push({ op: "add", text: y[j++]! });
  return [
    ...a.slice(0, head).map((text) => ({ op: "same" as const, text })),
    ...middle,
    ...a.slice(a.length - tail).map((text) => ({ op: "same" as const, text })),
  ];
}

export function hunks(lines: DiffLine[], context = 2): (DiffLine | null)[] {
  const keep = lines.map(() => false);
  lines.forEach((line, index) => {
    if (line.op === "same") return;
    for (let k = Math.max(0, index - context); k <= Math.min(lines.length - 1, index + context); k += 1) keep[k] = true;
  });
  const out: (DiffLine | null)[] = [];
  lines.forEach((line, index) => {
    if (keep[index]) out.push(line);
    else if (out.length === 0 || out[out.length - 1] !== null) out.push(null);
  });
  return out;
}
