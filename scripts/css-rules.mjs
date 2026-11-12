const PLACEMENT = [
  /^display$/,
  /^grid(?:-.*)?$/,
  /^(?:row-|column-)?gap$/,
  /^flex(?:-.*)?$/,
  /^order$/,
  /^align-.*$/,
  /^justify-.*$/,
  /^place-.*$/,
  /^position$/,
  /^inset(?:-.*)?$/,
  /^(?:top|right|bottom|left)$/,
  /^z-index$/,
  /^(?:min-|max-)?(?:width|height|inline-size|block-size)$/,
  /^aspect-ratio$/,
  /^margin(?:-.*)?$/,
  /^padding(?:-.*)?$/,
  /^overflow(?:-.*)?$/,
  /^container(?:-.*)?$/,
  /^contain(?:-.*)?$/,
  /^isolation$/,
  /^scroll-.*$/,
  /^overscroll-behavior(?:-.*)?$/,
  /^box-sizing$/,
  /^visibility$/,
  /^pointer-events$/,
  /^touch-action$/,
];

export const isPlacement = (property) =>
  property.startsWith("--") || PLACEMENT.some((pattern) => pattern.test(property));

export function appearanceDeclarations(css) {
  const found = [];
  const text = css.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, " "));
  let depth = 0;
  text.split("\n").forEach((line, index) => {
    const pieces = line.split(/([{};])/);
    let pending = "";
    for (const piece of pieces) {
      if (piece === "{") {
        depth += 1;
        pending = "";
      } else if (piece === "}") {
        if (depth > 0) check(pending, index);
        depth = Math.max(0, depth - 1);
        pending = "";
      } else if (piece === ";") {
        if (depth > 0) check(pending, index);
        pending = "";
      } else {
        pending += piece;
      }
    }
    if (depth > 0 && pending.trim() && /^\s*-?[a-z][a-z-]*\s*:/.test(pending) && !/[,{]\s*$/.test(pending)) {
      check(pending, index);
    }
  });
  return found;

  function check(piece, index) {
    const match = /^\s*(-?-?[a-z][a-z0-9-]*)\s*:(?!:)/.exec(piece);
    if (!match) return;
    const property = match[1];
    if (!/:\s*\S/.test(piece)) return;
    if (!isPlacement(property)) found.push({ line: index + 1, property });
  }
}

export function declaredClasses(css) {
  const classes = new Map();
  const text = css.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[^\n]/g, " "));
  text.split("\n").forEach((line, index) => {
    const selectors = line.includes("{")
      ? line.split("{").slice(0, -1).map((part) => part.split(/[};]/).at(-1) ?? "")
      : /,\s*$/.test(line)
        ? [line]
        : [];
    for (const selector of selectors) {
      for (const match of selector.matchAll(/\.([a-z][a-z0-9_-]*)/gi)) {
        if (!classes.has(match[1])) classes.set(match[1], index + 1);
      }
    }
  });
  return classes;
}

export function unusedClasses(css, sources) {
  const all = sources.join("\n");
  const prefixes = [...all.matchAll(/([a-z][a-z0-9-]*-)\$\{/g)].map((match) => match[1]);
  const words = new Set(all.match(/[a-z][a-z0-9_-]*/gi) ?? []);
  const unused = [];
  for (const [name, line] of declaredClasses(css)) {
    if (words.has(name)) continue;
    if (prefixes.some((prefix) => name.startsWith(prefix))) continue;
    unused.push({ line, name });
  }
  return unused;
}
