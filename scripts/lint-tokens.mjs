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
    message: "hex colour literal; use a variable from packages/ui/tokens.css",
  },
  {
    id: "inline-style",
    pattern: /style=\{\{(?!\s*(?:"--|'--|\[))/g,
    message: "inline style; style lives in packages/ui (only CSS variables are allowed)",
  },
  {
    id: "font-size-px",
    pattern: /font-size:\s*[\d.]+px/g,
    message: "font size in px; use a step of the scale (--text-*)",
  },
  {
    id: "raw-color",
    pattern: /\b(?:rgba?|hsla?)\((?!\s*var\()/g,
    message: "rgb()/hsl() colour literal; use a variable from packages/ui/tokens.css",
  },
  {
    id: "own-piece",
    pattern:
      /<(?:p|h[1-4]|div|section|main|button)\b[^>]*className="(?:[^"]*\s)?(?!widget-)[a-z]+-(?:screen|empty|empty-title|empty-detail|section-title|group-title|panel-title|block-title|note|hint|warning|fab|toast|toast-host)(?:\s[^"]*)?"/g,
    message: "own piece that already exists in packages/ui (Screen, EmptyState, Section, Heading, GroupLabel, Hint, Notice, CreateButton)",
    only: /\.tsx$/,
  },
  {
    id: "arbitrary-class",
    pattern: /\b[a-z-]+-\[[^\]]+\]/g,
    message: "arbitrary Tailwind class; use a token",
  },
  {
    id: "spacing-literal",
    pattern:
      /(?:^|[\s{;])(?:gap|row-gap|column-gap|padding(?:-[a-z]+)?|margin(?:-[a-z]+)?|inset(?:-[a-z]+)?)\s*:[^;]*?(?<![\w.-])(?!1px\b)(?:\d*\.)?\d+(?:px|rem|em)\b/g,
    message: "hand-written spacing; use a step of --space-*",
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
    message: "hand-written layer; use one of --z-*",
    only: /\.s?css$/,
    report: true,
  },
  {
    id: "own-base",
    pattern: /^\s*(?:html|body|::selection|:focus-visible)\s*[,{]/g,
    message: "own base; packages/ui/tokens.css already sets it",
    only: /\.s?css$/,
    report: true,
  },
  {
    id: "own-button",
    pattern: /<button\b[^>]*className="([a-z]+-[a-z-]*(?:btn|button))\b/g,
    message: "own button; use Button, IconButton or CreateButton from packages/ui",
    only: /\.tsx$/,
    report: true,
  },
  {
    id: "own-title",
    pattern: /<h[1-4]\b[^>]*className="((?!widget-)[a-z]+-[a-z0-9-]*)/g,
    message: "own heading; use Heading, Section or GroupLabel from packages/ui",
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
          rule: { id: "unknown-token", message: "variable nobody declares; the browser ignores the rule" },
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
        rule: { id: "app-css-placement", message: `appearance in the app; it belongs in packages/ui (the baseline allows ${allowed.appearance}, there are ${looks.length})` },
        match: one.property,
      });
    }
  }
  if (dead.length > allowed.unused) {
    for (const one of dead) {
      violations.push({
        rel,
        line: one.line,
        rule: { id: "app-css-unused", message: `class nobody uses in the app (the baseline allows ${allowed.unused}, there are ${dead.length})` },
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
  console.log(`app-css-baseline.json up to date: ${Object.keys(next).length} file(s) with debt.`);
} else if (lowered.length > 0) {
  console.log(`The CSS of ${lowered.join(", ")} has less debt than its baseline: lower the number with --update-baseline.\n`);
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
  console.log("Design debt per app (report, it does not block until its 1.0; --verbose for the detail):\n");
  console.log(line(header));
  for (const row of rows) console.log(line(row));
  console.log(`\n${debt.length} case(s) in ${rows.length} app(s).\n`);
  if (VERBOSE) {
    for (const v of debt) console.log(`${v.rel}:${v.line}  ${v.rule.id}  "${v.match.trim()}"  ${v.rule.message}`);
    console.log("");
  }
}

if (blocking.length > 0) {
  for (const v of blocking) {
    console.error(`${v.rel}:${v.line}  ${v.rule.id}  "${v.match.trim()}"  ${v.rule.message}`);
  }
  console.error(`\n${blocking.length} token violation(s). See docs/design-system.md.`);
  process.exit(1);
}

console.log(`lint:tokens ok · ${files.length} file(s) checked outside packages/ui`);
