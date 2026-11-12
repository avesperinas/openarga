import MarkdownIt from "markdown-it";
import type { PluginSimple, StateCore, StateInline, Token } from "markdown-it";
import footnote from "markdown-it-footnote";

const FRONTMATTER = /^---[ \t]*\r?\n(?:([\s\S]*?)\r?\n)?---[ \t]*(?:\r?\n|$)/;

export interface Split {
  frontmatter: string | null;
  body: string;
  offset: number;
}

export function split(content: string): Split {
  const match = FRONTMATTER.exec(content);
  if (!match) return { frontmatter: null, body: content, offset: 0 };
  return {
    frontmatter: match[1] ?? "",
    body: content.slice(match[0].length),
    offset: match[0].split("\n").length - 1,
  };
}

export interface ArgaBlock {
  start: number;
  end: number;
  inner: string;
}

const ARGA_BLOCK = /^%% arga %%[ \t]*\r?\n([\s\S]*?)^%% \/arga %%[ \t]*(?:\r?\n|$)/gm;

export function argaBlock(content: string): ArgaBlock | null {
  const head = FRONTMATTER.exec(content);
  ARGA_BLOCK.lastIndex = head ? head[0].length : 0;
  const match = ARGA_BLOCK.exec(content);
  if (!match) return null;
  return { start: match.index, end: match.index + match[0].length, inner: (match[1] ?? "").replace(/\n+$/, "") };
}

export interface WikiLink {
  target: string;
  heading: string | null;
  alias: string | null;
  embed: boolean;
}

export function wikilink(inner: string, embed = false): WikiLink | null {
  const clean = inner.replace(/\\\|/g, "|");
  const bar = clean.indexOf("|");
  const left = bar >= 0 ? clean.slice(0, bar) : clean;
  const alias = bar >= 0 ? clean.slice(bar + 1).trim() || null : null;
  const hash = left.indexOf("#");
  const target = (hash >= 0 ? left.slice(0, hash) : left).normalize("NFC").trim();
  const heading = hash >= 0 ? left.slice(hash + 1).trim() || null : null;
  if (!target && !heading) return null;
  return { target, heading, alias, embed };
}

export function linkText(link: WikiLink): string {
  if (link.alias) return link.alias;
  const name = link.target.split("/").pop() ?? link.target;
  if (!name) return link.heading ?? "";
  return link.heading ? `${name} › ${link.heading}` : name;
}

const IMAGE = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i;
const APP = /^[a-z][a-z0-9_]*:/;

export function slug(text: string): string {
  return text
    .normalize("NFC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
}

export interface RenderEnv {
  resolve?: (target: string) => string | null;
  fileUrl?: (name: string) => string | null;
  offset?: number;
  noteHref?: (id: string) => string;
  tagHref?: (tag: string) => string;
  tasks?: boolean;
  title?: string;
  appLink?: (target: string) => { href: string; title: string } | null;
}

const NOTEBOOK = "/notebook";
const noteHrefOf = (env: RenderEnv) => env.noteHref ?? ((id: string) => `${NOTEBOOK}/nota/${id}`);
const tagHrefOf = (env: RenderEnv) =>
  env.tagHref ?? ((tag: string) => `${NOTEBOOK}/buscar?tag=${encodeURIComponent(tag)}`);

const { escapeHtml: escape } = new MarkdownIt().utils;

function wikilinkRule(state: StateInline, silent: boolean): boolean {
  const start = state.pos;
  const embed = state.src.charCodeAt(start) === 0x21;
  const open = embed ? start + 1 : start;
  if (state.src.slice(open, open + 2) !== "[[") return false;
  const close = state.src.indexOf("]]", open + 2);
  if (close < 0) return false;
  const inner = state.src.slice(open + 2, close);
  if (!inner || inner.includes("\n") || inner.includes("[[")) return false;
  const link = wikilink(inner, embed);
  if (!link) return false;
  if (!silent) {
    const token = state.push("wikilink", "", 0);
    token.meta = link;
  }
  state.pos = close + 2;
  return true;
}

const TAG = /^#([\p{L}\p{N}_/-]+)/u;

function tagRule(state: StateInline, silent: boolean): boolean {
  const start = state.pos;
  if (state.src.charCodeAt(start) !== 0x23) return false;
  const before = start === 0 ? " " : state.src[start - 1]!;
  if (!/\s/.test(before)) return false;
  const match = TAG.exec(state.src.slice(start));
  if (!match || !/[^\d/_-]/.test(match[1]!)) return false;
  if (!silent) {
    const token = state.push("tag", "", 0);
    token.content = match[1]!.replace(/\/+$/, "");
  }
  state.pos = start + match[0].length;
  return true;
}

function highlightRule(state: StateInline, silent: boolean): boolean {
  const start = state.pos;
  if (state.src.slice(start, start + 2) !== "==") return false;
  const close = state.src.indexOf("==", start + 2);
  if (close <= start + 2) return false;
  const inner = state.src.slice(start + 2, close);
  if (inner.includes("\n") || /^\s|\s$/.test(inner)) return false;
  if (!silent) {
    state.push("mark_open", "mark", 1);
    const text = state.push("text", "", 0);
    text.content = inner;
    state.push("mark_close", "mark", -1);
  }
  state.pos = close + 2;
  return true;
}

const CALLOUT = /^\[!([\w-]+)\]([+-]?)[ \t]*(.*)$/;

function callouts(state: StateCore): void {
  const tokens = state.tokens;
  for (let i = 0; i < tokens.length - 2; i += 1) {
    const open = tokens[i]!;
    if (open.type !== "blockquote_open") continue;
    const paragraph = tokens[i + 1]!;
    const inline = tokens[i + 2]!;
    if (paragraph.type !== "paragraph_open" || inline.type !== "inline") continue;
    const [first, ...rest] = inline.content.split("\n");
    const match = CALLOUT.exec(first ?? "");
    if (!match) continue;
    const kind = match[1]!.toLowerCase();
    open.attrJoin("class", "mn-callout");
    open.attrSet("data-callout", kind);
    const title = new state.Token("callout_title", "", 0);
    title.content = match[3] || kind.charAt(0).toUpperCase() + kind.slice(1);
    tokens.splice(i + 1, 0, title);
    inline.content = rest.join("\n");
  }
}

function tasks(state: StateCore): void {
  const tokens = state.tokens;
  for (let i = 2; i < tokens.length; i += 1) {
    const inline = tokens[i]!;
    if (inline.type !== "inline" || tokens[i - 1]!.type !== "paragraph_open") continue;
    if (tokens[i - 2]!.type !== "list_item_open") continue;
    const match = /^\[([ xX])\][ \t]/.exec(inline.content);
    const first = inline.children?.[0];
    if (!match || !first || first.type !== "text") continue;
    first.content = first.content.replace(/^\[[ xX]\][ \t]/, "");
    const box = new state.Token("task", "", 0);
    box.meta = { done: match[1] !== " " };
    inline.children!.unshift(box);
    tokens[i - 2]!.attrJoin("class", "mn-task");
  }
}

function lines(state: StateCore): void {
  const offset = (state.env as RenderEnv).offset ?? 0;
  for (const token of state.tokens) {
    if (token.map && token.nesting === 1) token.attrSet("data-line", String(token.map[0] + offset));
  }
}

function make(): MarkdownIt {
  const md = new MarkdownIt({ html: false, linkify: true, breaks: true, typographer: false });
  md.use(footnote as unknown as PluginSimple);
  md.inline.ruler.before("link", "wikilink", wikilinkRule);
  md.inline.ruler.before("emphasis", "highlight", highlightRule);
  md.inline.ruler.push("tag", tagRule);
  md.core.ruler.after("block", "callouts", callouts);
  md.core.ruler.after("inline", "tasks", tasks);
  md.core.ruler.push("lines", lines);

  md.renderer.rules.wikilink = (tokens, idx, _options, env: RenderEnv) => {
    const link = tokens[idx]!.meta as WikiLink;
    const text = escape(linkText(link));
    if (APP.test(link.target)) {
      const note = env.resolve?.(link.target) ?? null;
      if (note) {
        const shown = escape(link.alias ?? env.appLink?.(link.target)?.title ?? link.target);
        return `<a class="mn-link" data-target="${escape(link.target)}" href="${escape(noteHrefOf(env)(note))}">${shown}</a>`;
      }
      const found = env.appLink?.(link.target) ?? null;
      if (found) {
        const shown = escape(link.alias ?? found.title);
        return `<a class="mn-app-link" href="${escape(found.href)}" data-app="${escape(link.target)}">${shown}</a>`;
      }
      return `<span class="mn-app-link" title="${escape(link.target)}">${text}</span>`;
    }
    if (link.embed && IMAGE.test(link.target)) {
      const url = env.fileUrl?.(link.target) ?? null;
      if (url) return `<img class="mn-image" src="${escape(url)}" alt="${escape(link.alias ?? link.target)}" loading="lazy">`;
      return `<span class="mn-file" data-missing="">${escape(link.target)}</span>`;
    }
    if (!link.target) {
      return `<a class="mn-link" href="#${escape(slug(link.heading ?? ""))}">${text}</a>`;
    }
    const id = env.resolve?.(link.target) ?? null;
    const attrs = [
      `data-target="${escape(link.target)}"`,
      link.heading ? `data-heading="${escape(link.heading)}"` : "",
      id ? `href="${escape(noteHrefOf(env)(id))}"` : `href="#" data-missing=""`,
    ]
      .filter(Boolean)
      .join(" ");
    const kind = link.embed ? "mn-link mn-embed" : "mn-link";
    return `<a class="${kind}" ${attrs}>${text}</a>`;
  };
  md.renderer.rules.tag = (tokens, idx, _options, env: RenderEnv) => {
    const tag = tokens[idx]!.content;
    return `<a class="mn-tag" href="${escape(tagHrefOf(env)(tag))}" data-tag="${escape(tag)}">#${escape(tag)}</a>`;
  };
  md.renderer.rules.callout_title = (tokens, idx) =>
    `<p class="mn-callout-title">${escape(tokens[idx]!.content)}</p>`;
  let taskIndex = 0;
  md.core.ruler.push("task_index", () => {
    taskIndex = 0;
  });
  md.renderer.rules.task = (tokens, idx, _options, env: RenderEnv) => {
    const checked = tokens[idx]!.meta.done ? " checked" : "";
    const index = taskIndex++;
    return env.tasks
      ? `<input class="mn-check" type="checkbox" data-task="${index}"${checked}> `
      : `<input class="mn-check" type="checkbox" disabled${checked}> `;
  };

  const heading = md.renderer.rules.heading_open;
  md.renderer.rules.heading_open = (tokens, idx, options, env, self) => {
    const inline = tokens[idx + 1];
    if (inline) tokens[idx]!.attrSet("id", slug(inline.content));
    return heading ? heading(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options);
  };
  const link = md.renderer.rules.link_open;
  md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const token = tokens[idx]!;
    if (/^https?:/i.test(token.attrGet("href") ?? "")) {
      token.attrSet("target", "_blank");
      token.attrSet("rel", "noopener noreferrer");
    }
    return link ? link(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options);
  };
  return md;
}

let instance: MarkdownIt | null = null;

export function toggleTask(content: string, index: number): string {
  const lines = content.split("\n");
  let fence: string | null = null;
  let seen = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]!;
    const opening = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (opening) {
      if (fence === null) fence = opening[1]!;
      else if (opening[1]![0] === fence[0] && opening[1]!.length >= fence.length) fence = null;
      continue;
    }
    if (fence !== null) continue;
    const task = /^(\s*(?:[-*+]|\d+[.)])\s+\[)([ xX])(\])/.exec(line);
    if (!task) continue;
    if (seen === index) {
      lines[i] = task[1] + (task[2] === " " ? "x" : " ") + task[3] + line.slice(task[0].length);
      return lines.join("\n");
    }
    seen += 1;
  }
  return content;
}

export function render(content: string, env: RenderEnv = {}): string {
  instance ??= make();
  const parts = split(content);
  let body = parts.body.replace(/%%[\s\S]*?%%/g, "");
  let offset = parts.offset;
  if (env.title) {
    const match = /^\s*#\s+(.+?)\s*#*\s*(?:\n|$)/.exec(body);
    const same = (text: string) => text.normalize("NFC").trim().toLowerCase();
    if (match && same(match[1]!) === same(env.title)) {
      offset += match[0].split("\n").length - 1;
      body = body.slice(match[0].length);
    }
  }
  return instance.render(body, { ...env, offset });
}

export type { Token };
