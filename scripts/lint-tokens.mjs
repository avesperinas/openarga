#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { join, relative, sep } from "node:path";

import { appearanceDeclarations, unusedClasses } from "./css-rules.mjs";

const ROOT = new URL("..", import.meta.url).pathname;
const SCANNED = ["shell", "modules"];
const ALLOWED = [
  "packages/ui",
  "modules/carrera/src/carrera/cv/templates",
];
const SKIP_DIRS = new Set(["node_modules", ".next", "dist", "storybook-static", ".git"]);
const EXTENSIONS = /\.(tsx?|jsx?|mjs|css|scss)$/;

const RULES = [
  {
    id: "hex-color",
    pattern: /#[0-9a-fA-F]{3,8}\b/g,
    message: "color hex literal; usa una variable de packages/ui/tokens.css",
  },
  {
    id: "inline-style",
    pattern: /style=\{\{(?!\s*(?:"--|'--|\[))/g,
    message: "estilo inline; el estilo vive en packages/ui (solo se permiten variables CSS)",
  },
  {
    id: "font-size-px",
    pattern: /font-size:\s*[\d.]+px/g,
    message: "tamaño de letra en px; usa un paso de la escala (--text-*)",
  },
  {
    id: "raw-color",
    pattern: /\b(?:rgba?|hsla?)\((?!\s*var\()/g,
    message: "color rgb()/hsl() literal; usa una variable de packages/ui/tokens.css",
  },
  {
    id: "own-piece",
    pattern:
      /<(?:p|h[1-4]|div|section|main|button)\b[^>]*className="(?:[^"]*\s)?(?!widget-)[a-z]+-(?:screen|empty|empty-title|empty-detail|section-title|group-title|panel-title|block-title|note|hint|warning|fab|toast|toast-host)(?:\s[^"]*)?"/g,
    message: "pieza propia que ya existe en packages/ui (Screen, EmptyState, Section, Heading, GroupLabel, Hint, Notice, CreateButton)",
    only: /\.tsx$/,
  },
  {
    id: "arbitrary-class",
    pattern: /\b[a-z-]+-\[[^\]]+\]/g,
    message: "clase arbitraria de Tailwind; usa un token",
  },
  {
    id: "spacing-literal",
    pattern:
      /(?:^|[\s{;])(?:gap|row-gap|column-gap|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?|inset(?:-[a-z]+)?)\s*:[^;]*?(?<![\w.-])(?!1px\b)(?:\d*\.)?\d+(?:px|rem|em)\b/g,
    message: "espacio escrito a mano; usa un paso de --space-*",
    only: /\.s?css$/,
    report: true,
  },
  {
    id: "radius-literal",
    pattern: /border(?:-[a-z]+)*-radius\s*:[^;]*?(?<![\w.-])(?:\d*\.)?\d+(?:px|rem|em)\b/g,
    message: "radio escrito a mano; usa --radius-surface, --radius-control o --radius-pill",
    only: /\.s?css$/,
    report: true,
  },
  {
    id: "z-index-literal",
    pattern: /z-index\s*:\s*(?:[2-9]|\d{2,})\b/g,
    message: "capa escrita a mano; usa una de --z-*",
    only: /\.s?css$/,
    report: true,
  },
  {
    id: "own-base",
    pattern: /^\s*(?:html|body|::selection|:focus-visible)\s*[,{]/g,
    message: "base propia; ya la pone packages/ui/tokens.css",
    only: /\.s?css$/,
    report: true,
  },
  {
    id: "own-button",
    pattern: /<button\b[^>]*className="([a-z]+-[a-z-]*(?:btn|button))\b/g,
    message: "botón propio; usa Button, IconButton o CreateButton de packages/ui",
    only: /\.tsx$/,
    report: true,
  },
  {
    id: "own-title",
    pattern: /<h[1-4]\b[^>]*className="((?!widget-)[a-z]+-[a-z0-9-]*)/g,
    message: "título propio; usa Heading, Section o GroupLabel de packages/ui",
    only: /\.tsx$/,
    report: true,
  },
];

const ONE_ZERO = ["library", "shopping", "chuping", "insights", "arca", "recipes", "goals", "study", "carrera", "planner", "notebook", "macros", "outings", "hub", "travel"];

const appOf = (rel) => (rel.startsWith("modules" + sep) ? rel.split(sep)[1] : rel.split(sep)[0]);
const VERBOSE = process.argv.includes("--verbose");

async function walk(dir, out = []) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) await walk(full, out);
    } else if (EXTENSIONS.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

const UI_CLASSES = new Set();
for (const file of await walk(join(ROOT, "packages/ui"))) {
  if (!/\.css$/.test(file)) continue;
  for (const match of readFileSync(file, "utf8").matchAll(/\.([a-z][a-z0-9-]*)/g)) UI_CLASSES.add(match[1]);
}

const isAllowed = (rel) => ALLOWED.some((a) => rel === a || rel.startsWith(a + sep));

const files = (await Promise.all(SCANNED.map((d) => walk(join(ROOT, d))))).flat();
const violations = [];

for (const file of files) {
  const rel = relative(ROOT, file);
  if (isAllowed(rel)) continue;
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, i) => {
    for (const rule of RULES) {
      if (rule.only && !rule.only.test(rel)) continue;
      rule.pattern.lastIndex = 0;
      const match = rule.pattern.exec(line);
      if (match && match[1] && UI_CLASSES.has(match[1])) continue;
      if (match) violations.push({ rel, line: i + 1, rule, match: match[0] });
    }
  });
}

const everything = (
  await Promise.all([...SCANNED, ...ALLOWED].map((d) => walk(join(ROOT, d))))
).flat();
const declared = new Set();
const sources = everything.map((file) => [file, readFileSync(file, "utf8")]);
for (const [, text] of sources) {
  for (const match of text.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) declared.add(match[1]);
  for (const match of text.matchAll(/["'`](--[a-zA-Z0-9-]+)["'`]/g)) declared.add(match[1]);
}
for (const [file, text] of sources) {
  const rel = relative(ROOT, file);
  text.split("\n").forEach((line, i) => {
    for (const match of line.matchAll(/var\((--[a-zA-Z0-9-]+)/g)) {
      if (!declared.has(match[1])) {
        violations.push({
          rel,
          line: i + 1,
          rule: { id: "unknown-token", message: "variable que no declara nadie; el navegador ignora la regla" },
          match: match[1],
        });
      }
    }
  });
}

const BASELINE_FILE = join(ROOT, "scripts/app-css-baseline.json");
const baseline = JSON.parse(readFileSync(BASELINE_FILE, "utf8"));
const UPDATE = process.argv.includes("--update-baseline");
const rootOf = (rel) => (rel.startsWith("modules" + sep) ? rel.split(sep).slice(0, 3).join(sep) : rel.split(sep)[0]);
const appCss = files.filter((file) => {
  const rel = relative(ROOT, file);
  return /\.css$/.test(rel) && (/^modules\/[^/]+\/ui\//.test(rel) || rel.startsWith("shell" + sep));
});
const measured = {};
const lowered = [];
for (const file of appCss) {
  const rel = relative(ROOT, file);
  const css = readFileSync(file, "utf8");
  const sources = files
    .filter((other) => other.startsWith(join(ROOT, rootOf(rel)) + sep) && /\.(?:tsx?|html)$/.test(other))
    .map((other) => readFileSync(other, "utf8"));
  const looks = appearanceDeclarations(css);
  const dead = unusedClasses(css, sources).filter((one) => !UI_CLASSES.has(one.name));
  measured[rel] = { appearance: looks.length, unused: dead.length };
  const allowed = baseline[rel] ?? { appearance: 0, unused: 0 };
  if (looks.length > allowed.appearance) {
    for (const one of looks) {
      violations.push({
        rel,
        line: one.line,
        rule: { id: "app-css-placement", message: `aspecto en la app; va en packages/ui (la base admite ${allowed.appearance}, hay ${looks.length})` },
        match: one.property,
      });
    }
  }
  if (dead.length > allowed.unused) {
    for (const one of dead) {
      violations.push({
        rel,
        line: one.line,
        rule: { id: "app-css-unused", message: `clase que no usa nadie en la app (la base admite ${allowed.unused}, hay ${dead.length})` },
        match: `.${one.name}`,
      });
    }
  }
  if (looks.length < allowed.appearance || dead.length < allowed.unused) lowered.push(rel);
}
if (UPDATE) {
  const next = Object.fromEntries(
    Object.entries(measured)
      .filter(([, counts]) => counts.appearance > 0 || counts.unused > 0)
      .sort(([a], [b]) => a.localeCompare(b)),
  );
  writeFileSync(BASELINE_FILE, `${JSON.stringify(next, null, 2)}\n`);
  console.log(`app-css-baseline.json al día: ${Object.keys(next).length} fichero(s) con deuda.`);
} else if (lowered.length > 0) {
  console.log(`El CSS de ${lowered.join(", ")} tiene menos deuda que su base: baja el número con --update-baseline.\n`);
}

const blocking = violations.filter((v) => !v.rule.report || ONE_ZERO.includes(appOf(v.rel)));
const debt = violations.filter((v) => !blocking.includes(v));

if (debt.length > 0) {
  const reportIds = RULES.filter((r) => r.report).map((r) => r.id);
  const byApp = new Map();
  for (const v of debt) {
    const app = appOf(v.rel);
    const row = byApp.get(app) ?? Object.fromEntries(reportIds.map((id) => [id, 0]));
    row[v.rule.id] += 1;
    byApp.set(app, row);
  }
  const rows = [...byApp.entries()]
    .map(([app, row]) => [app, ...reportIds.map((id) => row[id]), reportIds.reduce((n, id) => n + row[id], 0)])
    .sort((a, b) => b.at(-1) - a.at(-1));
  const header = ["app", ...reportIds, "total"];
  const widths = header.map((h, i) => Math.max(h.length, ...rows.map((r) => String(r[i]).length)));
  const line = (cells) => cells.map((c, i) => (i === 0 ? String(c).padEnd(widths[i]) : String(c).padStart(widths[i]))).join("  ");
  console.log("Deuda de diseño por app (informe, no bloquea hasta su 1.0; --verbose para el detalle):\n");
  console.log(line(header));
  for (const row of rows) console.log(line(row));
  console.log(`\n${debt.length} caso(s) en ${rows.length} app(s).\n`);
  if (VERBOSE) {
    for (const v of debt) console.log(`${v.rel}:${v.line}  ${v.rule.id}  "${v.match.trim()}"  ${v.rule.message}`);
    console.log("");
  }
}

if (blocking.length > 0) {
  for (const v of blocking) {
    console.error(`${v.rel}:${v.line}  ${v.rule.id}  "${v.match.trim()}"  ${v.rule.message}`);
  }
  console.error(`\n${blocking.length} violación(es) de tokens. Ver docs/design-system.md.`);
  process.exit(1);
}

console.log(`lint:tokens ok · ${files.length} fichero(s) revisado(s) fuera de packages/ui`);
