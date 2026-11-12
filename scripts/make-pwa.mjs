#!/usr/bin/env node

import { createHash } from "node:crypto";
import { deflateSync } from "node:zlib";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const TOKENS = join(ROOT, "packages/ui/tokens.css");

const SIZES = [
  { name: "icon-192.png", size: 192 },
  { name: "icon-512.png", size: 512 },
  { name: "apple-touch-icon.png", size: 180 },
];

function hex(name) {
  const tokens = readFileSync(TOKENS, "utf8");
  const match = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{3,8}|var\\(--([\\w-]+)\\))`).exec(tokens);
  if (!match) throw new Error(`token --${name} no encontrado en tokens.css`);
  return match[2] ? hex(match[2]) : match[1];
}

function token(name) {
  const value = hex(name).slice(1);
  const full = value.length === 3 ? [...value].map((c) => c + c).join("") : value;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

function png(size, paint) {
  const raw = Buffer.alloc(size * (1 + size * 4));
  for (let y = 0; y < size; y += 1) {
    const row = y * (1 + size * 4);
    raw[row] = 0;
    for (let x = 0; x < size; x += 1) {
      const [r, g, b, a] = paint(x, y);
      raw.set([r, g, b, a], row + 1 + x * 4);
    }
  }

  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const VIEW = 100;

const ARGA = {
  placement: { dy: 3, scale: 0.92 },
  background: "brand-arga-ground",
  strokes: [
    {
      color: "brand-arga-river",
      width: 9,
      curves: [
        [16, 55],
        [24, 55, 33, 54, 38, 48],
        [42, 43, 33, 38, 33, 30],
        [33, 22, 40, 16, 48, 16],
        [57, 16, 63, 22, 63, 30],
        [63, 38, 55, 42, 57, 48],
        [59, 54, 62, 62, 65, 68],
        [68, 75, 73, 76, 77, 73],
        [81, 70, 82, 64, 82, 58],
      ],
    },
  ],
  dots: [{ color: "brand-arga-orchard", cx: 44, cy: 70, r: 8 }],
};

const line = (x0, y0, x1, y1) => [
  [x0, y0],
  [x0 + (x1 - x0) / 3, y0 + (y1 - y0) / 3, x0 + (2 * (x1 - x0)) / 3, y0 + (2 * (y1 - y0)) / 3, x1, y1],
];

function familyOf(id) {
  const source = readFileSync(join(ROOT, "modules", id, "manifest.yaml"), "utf8");
  const match = /^\s+family:\s*(\w+)/m.exec(source);
  if (!match) throw new Error(`modules/${id}/manifest.yaml no declara ui.family`);
  return match[1];
}

function subpathsOf(d) {
  const tokens = d.match(/[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:e-?\d+)?/g);
  const subpaths = [];
  let current = null;
  let i = 0;
  let command = "";
  let [x, y] = [0, 0];
  let start = [0, 0];
  let control = null;
  const n = () => Number(tokens[i++]);
  const to = (x1, y1) => {
    current.push(line(x, y, x1, y1)[1]);
    [x, y] = [x1, y1];
  };
  while (i < tokens.length) {
    if (/[A-Za-z]/.test(tokens[i])) command = tokens[i++];
    const relative = command === command.toLowerCase();
    const ox = relative ? x : 0;
    const oy = relative ? y : 0;
    const previous = control;
    control = null;
    switch (command.toUpperCase()) {
      case "M": {
        [x, y] = [ox + n(), oy + n()];
        start = [x, y];
        current = [[x, y]];
        subpaths.push(current);
        command = relative ? "l" : "L";
        break;
      }
      case "L":
        to(ox + n(), oy + n());
        break;
      case "H":
        to((relative ? x : 0) + n(), y);
        break;
      case "V":
        to(x, (relative ? y : 0) + n());
        break;
      case "C": {
        const c = [ox + n(), oy + n(), ox + n(), oy + n(), ox + n(), oy + n()];
        current.push(c);
        [x, y] = [c[4], c[5]];
        control = [c[2], c[3]];
        break;
      }
      case "S": {
        const [cx1, cy1] = previous ? [2 * x - previous[0], 2 * y - previous[1]] : [x, y];
        const c = [cx1, cy1, ox + n(), oy + n(), ox + n(), oy + n()];
        current.push(c);
        [x, y] = [c[4], c[5]];
        control = [c[2], c[3]];
        break;
      }
      case "Q": {
        const [qx, qy, x1, y1] = [ox + n(), oy + n(), ox + n(), oy + n()];
        current.push([x + (2 / 3) * (qx - x), y + (2 / 3) * (qy - y), x1 + (2 / 3) * (qx - x1), y1 + (2 / 3) * (qy - y1), x1, y1]);
        [x, y] = [x1, y1];
        break;
      }
      case "A": {
        const [rx, ry, rotation, large, sweep] = [n(), n(), n(), n(), n()];
        const [x1, y1] = [ox + n(), oy + n()];
        for (const c of arcCurves(x, y, rx, ry, rotation, large, sweep, x1, y1)) current.push(c);
        [x, y] = [x1, y1];
        break;
      }
      case "Z":
        if (x !== start[0] || y !== start[1]) to(...start);
        command = "";
        break;
      default:
        throw new Error(`camino no soportado: ${d}`);
    }
  }
  return subpaths;
}

function arcCurves(x0, y0, rx, ry, rotation, large, sweep, x1, y1) {
  if (rx === 0 || ry === 0) return [line(x0, y0, x1, y1)[1]];
  const phi = (rotation * Math.PI) / 180;
  const [cos, sin] = [Math.cos(phi), Math.sin(phi)];
  const dx = (x0 - x1) / 2;
  const dy = (y0 - y1) / 2;
  const xp = cos * dx + sin * dy;
  const yp = -sin * dx + cos * dy;
  let [ax, ay] = [Math.abs(rx), Math.abs(ry)];
  const lambda = (xp * xp) / (ax * ax) + (yp * yp) / (ay * ay);
  if (lambda > 1) [ax, ay] = [ax * Math.sqrt(lambda), ay * Math.sqrt(lambda)];
  const sign = large === sweep ? -1 : 1;
  const numerator = ax * ax * ay * ay - ax * ax * yp * yp - ay * ay * xp * xp;
  const factor = sign * Math.sqrt(Math.max(0, numerator / (ax * ax * yp * yp + ay * ay * xp * xp)));
  const cxp = (factor * ax * yp) / ay;
  const cyp = (-factor * ay * xp) / ax;
  const cx = cos * cxp - sin * cyp + (x0 + x1) / 2;
  const cy = sin * cxp + cos * cyp + (y0 + y1) / 2;
  const angle = (ux, uy, vx, vy) => Math.atan2(ux * vy - uy * vx, ux * vx + uy * vy);
  const theta = angle(1, 0, (xp - cxp) / ax, (yp - cyp) / ay);
  let delta = angle((xp - cxp) / ax, (yp - cyp) / ay, (-xp - cxp) / ax, (-yp - cyp) / ay);
  if (!sweep && delta > 0) delta -= 2 * Math.PI;
  if (sweep && delta < 0) delta += 2 * Math.PI;
  const pieces = Math.ceil(Math.abs(delta) / (Math.PI / 2));
  const step = delta / pieces;
  const k = (4 / 3) * Math.tan(step / 4);
  const point = (t) => [cx + ax * Math.cos(t) * cos - ay * Math.sin(t) * sin, cy + ax * Math.cos(t) * sin + ay * Math.sin(t) * cos];
  const tangent = (t) => [-ax * Math.sin(t) * cos - ay * Math.cos(t) * sin, -ax * Math.sin(t) * sin + ay * Math.cos(t) * cos];
  const curves = [];
  for (let piece = 0; piece < pieces; piece += 1) {
    const t0 = theta + piece * step;
    const t1 = t0 + step;
    const [p0, p1] = [point(t0), point(t1)];
    const [d0, d1] = [tangent(t0), tangent(t1)];
    curves.push([p0[0] + k * d0[0], p0[1] + k * d0[1], p1[0] - k * d1[0], p1[1] - k * d1[1], p1[0], p1[1]]);
  }
  return curves;
}

const disc = (cx, cy, r) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0z`;
const oval = (cx, cy, rx, ry) => `M${cx - rx} ${cy}a${rx} ${ry} 0 1 0 ${2 * rx} 0a${rx} ${ry} 0 1 0 ${-2 * rx} 0z`;
const box = (x, y, w, h, r) =>
  `M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}z`;
const band = (cx, cy, inner, outer, from, to) => {
  const at = (r, deg) => [cx + r * Math.sin((deg * Math.PI) / 180), cy - r * Math.cos((deg * Math.PI) / 180)];
  const large = to - from > 180 ? 1 : 0;
  const [a, b, c, e] = [at(outer, from), at(outer, to), at(inner, to), at(inner, from)];
  return `M${a[0]} ${a[1]}A${outer} ${outer} 0 ${large} 1 ${b[0]} ${b[1]}L${c[0]} ${c[1]}A${inner} ${inner} 0 ${large} 0 ${e[0]} ${e[1]}z`;
};

const fill = (role, d, opacity = 1) => ({ role, d, opacity });
const stroke = (role, d, width, opacity = 1) => ({ role, d, width, opacity });

const FILLED = {
  planner: [
    fill("P", box(22, 27, 56, 51, 11)),
    fill("A", "M22 38a11 11 0 0 1 11-11h34a11 11 0 0 1 11 11v5H22z"),
    fill("A", box(34, 20, 7, 15, 3.5)),
    fill("A", box(59, 20, 7, 15, 3.5)),
    ...[[31, 51], [45.5, 51], [31, 63], [45.5, 63], [60, 63]].map(([x, y]) => fill("G", box(x, y, 9, 8, 2.5))),
    fill("A", box(60, 51, 9, 8, 2.5)),
  ],
  recipes: [
    fill("P", disc(36, 43, 12)),
    fill("P", disc(64, 43, 12)),
    fill("P", disc(50, 36, 15)),
    fill("P", box(33, 42, 34, 22, 0.01)),
    fill("A", box(33, 62, 34, 13, 4)),
  ],
  macros: [
    fill("P", band(50, 50, 16, 30, 4, 166)),
    fill("A", band(50, 50, 16, 30, 176, 280)),
    fill("P", band(50, 50, 16, 30, 290, 354), 0.6),
  ],
  vitals: [
    fill("P", "M50 77C30 63 21 53 21 41c0-9 7-16 16-16 6 0 10 3 13 7 3-4 7-7 13-7 9 0 16 7 16 16 0 12-9 22-29 36z"),
    stroke("A", "M22 48h14l5-9 7 18 6-12 4 3h20", 5.5),
  ],
  training: [
    fill("A", box(36, 46, 28, 8, 3)),
    fill("P", box(24, 32, 12, 36, 5)),
    fill("P", box(64, 32, 12, 36, 5)),
    fill("P", box(16, 37, 7, 26, 3.5)),
    fill("P", box(77, 37, 7, 26, 3.5)),
  ],
  goals: [
    fill("P", disc(46, 54, 25)),
    fill("G", disc(46, 54, 16)),
    fill("P", disc(46, 54, 8)),
    stroke("A", "M48 52 74 26", 6),
    stroke("A", "M47 42v11h11", 6),
  ],
  shopping: [
    stroke("A", "M34 45c0-15 7-21 16-21s16 6 16 21", 7),
    fill("P", "M19 44h62a3 3 0 0 1 3 3.6L78 74a5 5 0 0 1-5 4H27a5 5 0 0 1-5-4l-6-26.4A3 3 0 0 1 19 44z"),
    ...[33, 47, 61].map((x) => fill("G", box(x, 53, 6, 16, 3))),
  ],
  study: [
    fill("A", "M32 50v12c0 7 36 7 36 0V50L50 58z"),
    fill("P", "M50 24 84 40 50 56 16 40z"),
    stroke("A", "M50 40 74 46v16", 4.5),
    fill("A", disc(74, 66, 5)),
  ],
  notebook: [
    stroke("P", "M36 66 58 34M36 66l30 4M58 34l8 36", 5),
    fill("P", disc(58, 32, 12)),
    fill("A", disc(34, 66, 10)),
    fill("P", disc(68, 70, 8)),
  ],
  outings: [
    fill("A", "M50 30c4-8 12-11 20-9-2 8-9 12-17 12z"),
    stroke("A", "M50 22v12", 4.5),
    ...[[38, 43], [50, 43], [62, 43], [44, 56], [56, 56], [50, 69]].map(([cx, cy]) => fill("P", disc(cx, cy, 8.5))),
  ],
  travel: [
    fill("P", "M17 48 82 22 66 77 49 60z"),
    fill("A", "M49 60 82 22 42 53z"),
    fill("A", "M49 60 46 74 55 65z"),
  ],
  library: [
    fill("P", "M48 30c-9-5-20-6-30-4v48c10-2 21-1 30 4z"),
    fill("P", "M52 30c9-5 20-6 30-4v48c-10-2-21-1-30 4z"),
    stroke("A", "M26 38c6-1 12 0 15 2M26 48c6-1 12 0 15 2M26 58c6-1 12 0 15 2M74 38c-6-1-12 0-15 2M74 48c-6-1-12 0-15 2", 3.5),
  ],
  money: [
    fill("P", box(21, 56, 13, 21, 4)),
    fill("P", box(43.5, 45, 13, 32, 4)),
    fill("P", box(66, 34, 13, 43, 4)),
    stroke("A", "M22 44 40 30l10 7 22-16", 5.5),
    stroke("A", "M64 20h9v9", 5.5),
  ],
  hub: [
    fill("P", box(38, 20, 7, 17, 3.5)),
    fill("P", box(55, 20, 7, 17, 3.5)),
    fill("P", "M30 35h40v10c0 11-9 20-20 20s-20-9-20-20z"),
    stroke("A", "M50 64v6c0 5 4 9 9 9h9", 7),
    fill("G", disc(50, 46, 4.5)),
  ],
  insights: [
    fill("P", "M31 49 32.5 28.5 46 38.5z"),
    stroke("P", "M31 49 32.5 28.5 46 38.5z", 3),
    fill("P", "M69 49 67.5 28.5 54 38.5z"),
    stroke("P", "M69 49 67.5 28.5 54 38.5z", 3),
    fill("P", oval(50, 56, 21, 18.5)),
  ],
};

function shade(hexColor, amount) {
  const value = parseInt(hexColor.slice(1), 16);
  const channels = [value >> 16, (value >> 8) & 255, value & 255].map((c) =>
    Math.round(amount < 0 ? c * (1 + amount) : c + (255 - c) * amount),
  );
  return `#${channels.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

function finish(style, family, id) {
  if (id === "insights") {
    const night = hex("mark-night");
    const mist = hex("mark-mist");
    return { top: shade(night, 0.08), bottom: night, P: mist, A: mist, G: night };
  }
  const base = hex(`family-${family}`);
  if (style === "solid") return { top: shade(base, 0.18), bottom: shade(base, -0.12), P: "#ffffff", A: shade(base, -0.38), G: shade(base, -0.02) };
  if (style === "ink") {
    const ink = hex("mark-ink");
    return { top: shade(ink, 0.06), bottom: shade(ink, -0.25), P: base, A: hex("mark-paper"), G: shade(ink, -0.08) };
  }
  const cream = hex("mark-cream");
  return { top: cream, bottom: cream, P: base, A: shade(base, 0.55), G: cream };
}

const STYLES = ["solid", "ink", "paper"];
const FILLED_PLACEMENT = { dy: 0, scale: 0.94 };

function styled(id) {
  const family = familyOf(id);
  return Object.fromEntries(STYLES.map((style) => [style, { id, style, layers: FILLED[id], colors: finish(style, family, id) }]));
}

function svgFilled({ id, style, layers, colors }) {
  const fmt = (n) => String(Math.round(n * 1000) / 1000);
  const ground = colors.top === colors.bottom ? colors.top : `url(#${id}-${style})`;
  const defs =
    colors.top === colors.bottom
      ? ""
      : `<defs><linearGradient id="${id}-${style}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${colors.top}"/><stop offset="1" stop-color="${colors.bottom}"/></linearGradient></defs>`;
  const body = layers
    .map((layer) => {
      const d = subpathsOf(layer.d)
        .map((curves) => pathOf(curves))
        .join(" ");
      const opacity = layer.opacity < 1 ? ` opacity="${fmt(layer.opacity)}"` : "";
      return layer.width
        ? `<path d="${d}" fill="none" stroke="${colors[layer.role]}" stroke-width="${layer.width}" stroke-linecap="round" stroke-linejoin="round"${opacity}/>`
        : `<path d="${d}" fill="${colors[layer.role]}"${opacity}/>`;
    })
    .join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${VIEW} ${VIEW}">${defs}` +
    `<rect width="${VIEW}" height="${VIEW}" rx="22" fill="${ground}"/>` +
    `<g transform="${transformOf(FILLED_PLACEMENT)}">${body}</g></svg>\n`
  );
}

const rgb = (hexColor) => [1, 3, 5].map((i) => parseInt(hexColor.slice(i, i + 2), 16));

function paintFilled({ layers, colors }) {
  const place = placer(FILLED_PLACEMENT);
  const { scale } = FILLED_PLACEMENT;
  const shapes = layers.map((layer) => {
    const polygons = subpathsOf(layer.d).map((curves) => flatten(curves, place));
    return { polygons, half: layer.width ? (layer.width * scale) / 2 : 0, color: rgb(colors[layer.role]), opacity: layer.opacity };
  });
  const [top, bottom] = [rgb(colors.top), rgb(colors.bottom)];
  const mix = (a, b, alpha) => a.map((channel, i) => channel + (b[i] - channel) * alpha);

  return (size) => {
    const unit = VIEW / size;
    const SUB = 4;
    const coverage = shapes.map((shape) => {
      const cover = new Float32Array(size * size);
      if (shape.half) {
        for (let py = 0; py < size; py += 1) {
          for (let px = 0; px < size; px += 1) {
            const x = (px + 0.5) * unit;
            const y = (py + 0.5) * unit;
            let distance = Infinity;
            for (const polyline of shape.polygons) {
              for (let i = 1; i < polyline.length; i += 1) distance = Math.min(distance, distanceToSegment(x, y, polyline[i - 1], polyline[i]));
            }
            cover[py * size + px] = Math.max(0, Math.min(1, (shape.half - distance) / unit + 0.5));
          }
        }
        return cover;
      }
      const edges = [];
      for (const polygon of shape.polygons) {
        for (let i = 0; i < polygon.length; i += 1) {
          const a = polygon[i];
          const b = polygon[(i + 1) % polygon.length];
          if (a[1] !== b[1]) edges.push([a[0] / unit, a[1] / unit, b[0] / unit, b[1] / unit]);
        }
      }
      for (let py = 0; py < size; py += 1) {
        for (let sub = 0; sub < SUB; sub += 1) {
          const y = py + (sub + 0.5) / SUB;
          const crossings = [];
          for (const [x0, y0, x1, y1] of edges) {
            if ((y >= y0 && y < y1) || (y >= y1 && y < y0)) crossings.push([x0 + ((y - y0) / (y1 - y0)) * (x1 - x0), y1 > y0 ? 1 : -1]);
          }
          crossings.sort((a, b) => a[0] - b[0]);
          let winding = 0;
          for (let k = 0; k < crossings.length - 1; k += 1) {
            winding += crossings[k][1];
            if (winding === 0) continue;
            const from = Math.max(0, crossings[k][0]);
            const to = Math.min(size, crossings[k + 1][0]);
            for (let px = Math.floor(from); px < Math.ceil(to); px += 1) {
              const overlap = Math.min(to, px + 1) - Math.max(from, px);
              if (overlap > 0) cover[py * size + px] += overlap / SUB;
            }
          }
        }
      }
      return cover;
    });
    return (px, py) => {
      let color = mix(top, bottom, (py + 0.5) / size);
      shapes.forEach((shape, index) => {
        const alpha = Math.min(1, coverage[index][py * size + px]) * shape.opacity;
        if (alpha > 0) color = mix(color, shape.color, alpha);
      });
      return [...color.map(Math.round), 255];
    };
  };
}

const APPS = [
  {
    dir: "shell/public",
    base: "/",
    name: "OpenArga",
    description: "Your system, your data.",
    geometry: ARGA,
  },
  {
    dir: "modules/training/ui/public",
    base: "/training/",
    name: "Training",
    description: "Strength training, one tap per set.",
    styles: styled("training"),
  },
  {
    dir: "modules/recipes/ui/public",
    base: "/recipes/",
    name: "Recipes",
    description: "Your home cookbook, with the macros worked out.",
    styles: styled("recipes"),
  },
  {
    dir: "modules/money/ui/public",
    base: "/money/",
    name: "Finance",
    description: "Your accounts, shared expenses and what everything is worth.",
    styles: styled("money"),
  },
  {
    dir: "modules/hub/ui/public",
    base: "/hub/",
    name: "Connections",
    description: "Everything that comes from outside, in one place.",
    styles: styled("hub"),
  },
  {
    dir: "modules/shopping/ui/public",
    base: "/shopping/",
    name: "Shopping",
    description: "The shopping list that remembers what you buy.",
    styles: styled("shopping"),
  },
  {
    dir: "modules/library/ui/public",
    base: "/library/",
    name: "Books",
    description: "The books you read.",
    styles: styled("library"),
  },
  {
    dir: "modules/study/ui/public",
    base: "/study/",
    name: "Study",
    description: "What you study.",
    styles: styled("study"),
  },
  {
    dir: "modules/vitals/ui/public",
    base: "/vitals/",
    name: "Health",
    description: "Steps, sleep, weight and lab results.",
    styles: styled("vitals"),
  },
  {
    dir: "modules/travel/ui/public",
    base: "/travel/",
    name: "Travel",
    description: "Trips: ideas, plans and the ones you made.",
    styles: styled("travel"),
  },
  {
    dir: "modules/planner/ui/public",
    base: "/planner/",
    name: "Calendar",
    description: "Your calendar: your events, what repeats and what arrives on its own.",
    styles: styled("planner"),
  },
  {
    dir: "modules/goals/ui/public",
    base: "/goals/",
    name: "Goals",
    description: "What you set out to do and what you have to do.",
    styles: styled("goals"),
  },
  {
    dir: "modules/notebook/ui/public",
    base: "/notebook/",
    name: "Notes",
    description: "What you know: your notes, linked.",
    styles: styled("notebook"),
  },
  {
    dir: "modules/macros/ui/public",
    base: "/macros/",
    name: "Nutrition",
    description: "What you eat and drink, with its macros and micros.",
    styles: styled("macros"),
  },
  {
    dir: "modules/outings/ui/public",
    base: "/outings/",
    name: "Outings",
    description: "What is on near you and what you want to do.",
    styles: styled("outings"),
  },
  {
    dir: "modules/insights/ui/public",
    base: "/insights/",
    name: "Insights",
    description: "What your data says, every week.",
    styles: styled("insights"),
  },
];

const placer = ({ dy, scale }) => ([x, y]) => [50 + scale * (x - 50), 50 + scale * (y + dy - 50)];
const transformOf = ({ dy, scale }) => `translate(50 50) scale(${scale}) translate(-50 ${-50 + dy})`;

function pathOf(curves) {
  const [[x0, y0], ...rest] = curves;
  const format = (n) => String(Math.round(n * 1000) / 1000);
  return `M${format(x0)} ${format(y0)} ` + rest.map((c) => `C${c.map(format).join(" ")}`).join(" ");
}

function svgMark(geometry, background) {
  const strokes = geometry.strokes
    .map(
      (stroke) =>
        `<path d="${pathOf(stroke.curves)}" fill="none" stroke="${hex(stroke.color)}" stroke-width="${stroke.width}" stroke-linecap="round" stroke-linejoin="round"/>`,
    )
    .join("");
  const dots = geometry.dots
    .map((dot) => `<circle cx="${dot.cx}" cy="${dot.cy}" r="${dot.r}" fill="${hex(dot.color)}"/>`)
    .join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${VIEW} ${VIEW}">` +
    `<rect width="${VIEW}" height="${VIEW}" rx="22" fill="${background}"/>` +
    `<g transform="${transformOf(geometry.placement)}">${strokes}${dots}</g></svg>\n`
  );
}

function flatten(curves, place) {
  const points = [place(curves[0])];
  let [px, py] = curves[0];
  for (const [c1x, c1y, c2x, c2y, x, y] of curves.slice(1)) {
    for (let step = 1; step <= 32; step += 1) {
      const t = step / 32;
      const u = 1 - t;
      points.push(
        place([
          u * u * u * px + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * x,
          u * u * u * py + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * y,
        ]),
      );
    }
    [px, py] = [x, y];
  }
  return points;
}

function distanceToSegment(x, y, [ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
}

function mark(geometry, background) {
  const place = placer(geometry.placement);
  const { scale } = geometry.placement;
  const strokes = geometry.strokes.map((stroke) => ({
    polyline: flatten(stroke.curves, place),
    half: (stroke.width * scale) / 2,
    color: token(stroke.color),
  }));
  const dots = geometry.dots.map((dot) => {
    const [cx, cy] = place([dot.cx, dot.cy]);
    return { cx, cy, r: dot.r * scale, color: token(dot.color) };
  });
  const mix = (a, b, alpha) => a.map((channel, i) => Math.round(channel + (b[i] - channel) * alpha));

  return (size) => {
    const unit = VIEW / size;
    const cover = (inside) => Math.max(0, Math.min(1, inside / unit + 0.5));
    return (px, py) => {
      const x = (px + 0.5) * unit;
      const y = (py + 0.5) * unit;
      let color = background;
      for (const stroke of strokes) {
        let distance = Infinity;
        for (let i = 1; i < stroke.polyline.length; i += 1) {
          distance = Math.min(distance, distanceToSegment(x, y, stroke.polyline[i - 1], stroke.polyline[i]));
        }
        color = mix(color, stroke.color, cover(stroke.half - distance));
      }
      for (const dot of dots) {
        color = mix(color, dot.color, cover(dot.r - Math.hypot(x - dot.cx, y - dot.cy)));
      }
      return [...color, 255];
    };
  };
}

function manifest(app, background, versions) {
  const icon = (file) => `${app.base}${file}?v=${versions[file]}`;
  return JSON.stringify(
    {
      name: app.name,
      short_name: app.name,
      description: app.description,
      start_url: app.base,
      ...(app.base === "/" ? {} : { scope: app.base, id: app.base }),
      display: "standalone",
      orientation: "portrait",
      background_color: background,
      theme_color: background,
      icons: [
        { src: icon("icon-192.png"), sizes: "192x192", type: "image/png", purpose: "any" },
        { src: icon("icon-512.png"), sizes: "512x512", type: "image/png", purpose: "any" },
        { src: icon("icon-512.png"), sizes: "512x512", type: "image/png", purpose: "maskable" },
        { src: icon("icon.svg"), sizes: "any", type: "image/svg+xml", purpose: "any" },
      ],
    },
    null,
    2,
  );
}

function filledAssets(app) {
  const solid = app.styles.solid;
  const paint = paintFilled(solid);
  const svg = Buffer.from(svgFilled(solid));
  const icons = [
    ...SIZES.map(({ name, size }) => ({ dir: app.dir, name, body: png(size, paint(size)) })),
    { dir: app.dir, name: "icon.svg", body: svg },
  ];
  const versions = Object.fromEntries(
    icons.map(({ name, body }) => [name, createHash("sha256").update(body).digest("hex").slice(0, 10)]),
  );
  return [
    ...icons,
    ...STYLES.map((style) => ({ dir: app.dir, name: `icon-${style}.svg`, body: Buffer.from(svgFilled(app.styles[style])) })),
    { dir: app.dir, name: "manifest.webmanifest", body: Buffer.from(manifest(app, solid.colors.bottom, versions) + "\n") },
  ];
}

const assets = APPS.flatMap((app) => {
  if (app.styles) return filledAssets(app);
  const ground = app.geometry.background ?? "bg-base";
  const background = hex(ground);
  const paint = mark(app.geometry, token(ground));
  const icons = [
    ...SIZES.map(({ name, size }) => ({ dir: app.dir, name, body: png(size, paint(size)) })),
    { dir: app.dir, name: "icon.svg", body: Buffer.from(svgMark(app.geometry, background)) },
  ];
  const versions = Object.fromEntries(
    icons.map(({ name, body }) => [name, createHash("sha256").update(body).digest("hex").slice(0, 10)]),
  );
  return [
    ...icons,
    { dir: app.dir, name: "manifest.webmanifest", body: Buffer.from(manifest(app, background, versions) + "\n") },
  ];
});

const check = process.argv.includes("--check");
const stale = [];

for (const { dir, name, body } of assets) {
  const path = join(ROOT, dir, name);
  if (check) {
    let current;
    try {
      current = readFileSync(path);
    } catch {
      current = Buffer.alloc(0);
    }
    if (!current.equals(body)) stale.push(join(dir, name));
  } else {
    mkdirSync(join(ROOT, dir), { recursive: true });
    writeFileSync(path, body);
    console.log(`${join(dir, name)}  ${body.length} bytes`);
  }
}

if (check && stale.length > 0) {
  console.error(
    `assets de la PWA desfasados respecto a tokens.css: ${stale.join(", ")}\n` +
      `Regenera con \`node scripts/make-pwa.mjs\` y commitea el resultado.`,
  );
  process.exit(1);
}
if (check) console.log(`pwa ok · ${assets.length} asset(s) al día con tokens.css`);
