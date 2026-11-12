import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import * as React from "react";

import type { Graph } from "./api";

interface Node extends SimulationNodeDatum {
  id: string;
  title: string;
  folder: string;
  links: number;
  depth: number | null;
  r: number;
}

type Link = SimulationLinkDatum<Node>;

interface Props {
  graph: Graph;
  focus?: string | null;
  onOpen: (id: string) => void;
  highlight?: (node: { title: string; folder: string }) => boolean;
  compact?: boolean;
}

function palette(element: HTMLElement): string[] {
  return Array.from({ length: 10 }, (_, i) => token(element, `--tone-${i + 1}`)).filter(Boolean);
}

function token(element: HTMLElement, name: string): string {
  const probe = document.createElement("span");
  probe.style.color = `var(${name})`;
  probe.style.display = "none";
  element.parentElement?.appendChild(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  return value || getComputedStyle(element).getPropertyValue(name).trim();
}

function fontOf(element: HTMLElement): string {
  return getComputedStyle(element).getPropertyValue("--font-sans").trim();
}

export function toneIndex(folder: string, tones: number): number {
  let hash = 0;
  for (const char of folder.toLowerCase()) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return folder ? hash % tones : -1;
}

export function GraphView({ graph, focus = null, onOpen, highlight, compact = false }: Props) {
  const canvas = React.useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = React.useState<Node | null>(null);
  const state = React.useRef({ x: 0, y: 0, k: 1, nodes: [] as Node[], links: [] as Link[], hover: null as Node | null });
  const draw = React.useRef<() => void>(() => undefined);
  const openRef = React.useRef(onOpen);
  openRef.current = onOpen;
  const highlightRef = React.useRef(highlight);
  highlightRef.current = highlight;

  React.useEffect(() => {
    const element = canvas.current!;
    const context = element.getContext("2d")!;
    const nodes: Node[] = graph.nodes.map((n) => ({ ...n, r: 3 + Math.min(9, Math.sqrt(n.links) * 1.6) }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links: Link[] = graph.edges
      .filter(([a, b]) => byId.has(a) && byId.has(b))
      .map(([a, b]) => ({ source: byId.get(a)!, target: byId.get(b)! }));
    const neighbours = new Map<string, Set<string>>();
    for (const [a, b] of graph.edges) {
      if (!neighbours.has(a)) neighbours.set(a, new Set());
      if (!neighbours.has(b)) neighbours.set(b, new Set());
      neighbours.get(a)!.add(b);
      neighbours.get(b)!.add(a);
    }
    state.current = { ...state.current, nodes, links, x: 0, y: 0, k: 1 };

    const tones = palette(element);
    const fg = token(element, "--fg");
    const muted = token(element, "--fg-muted");
    const accent = token(element, "--accent");
    const deep = token(element, "--bg-base");
    const font = fontOf(element) || "sans-serif";
    const colourOf = new Map<string, string>();
    for (const node of nodes) {
      const tone = toneIndex(node.folder, tones.length);
      colourOf.set(node.id, tone >= 0 ? tones[tone]! : muted);
    }
    const glow = nodes.length <= 3000;
    const halos = new Map<string, HTMLCanvasElement>();
    const halo = (fill: string): HTMLCanvasElement => {
      let made = halos.get(fill);
      if (!made) {
        made = document.createElement("canvas");
        made.width = made.height = 64;
        const pen = made.getContext("2d")!;
        const light = pen.createRadialGradient(32, 32, 0, 32, 32, 32);
        light.addColorStop(0, fill);
        light.addColorStop(1, "transparent");
        pen.globalAlpha = 0.55;
        pen.fillStyle = light;
        pen.fillRect(0, 0, 64, 64);
        halos.set(fill, made);
      }
      return made;
    };
    const ratio = Math.min(window.devicePixelRatio || 1, 2);

    const paint = () => {
      const { x, y, k, hover: over } = state.current;
      const width = element.clientWidth;
      const height = element.clientHeight;
      if (element.width !== Math.round(width * ratio) || element.height !== Math.round(height * ratio)) {
        element.width = Math.round(width * ratio);
        element.height = Math.round(height * ratio);
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.globalAlpha = 1;
      context.fillStyle = deep;
      context.fillRect(0, 0, width, height);
      const nebula = context.createRadialGradient(width / 2 + x, height / 2 + y, 0, width / 2 + x, height / 2 + y, Math.max(width, height) * 0.6);
      nebula.addColorStop(0, accent);
      nebula.addColorStop(1, deep);
      context.globalAlpha = 0.16;
      context.fillStyle = nebula;
      context.fillRect(0, 0, width, height);
      context.globalAlpha = 1;
      context.translate(width / 2 + x, height / 2 + y);
      context.scale(k, k);
      const lit = over ? neighbours.get(over.id) ?? new Set<string>() : null;
      const matches = highlightRef.current;
      const dim = (n: Node) => (matches && !matches(n)) || (lit && n !== over && !lit.has(n.id));

      const strokes = new Map<string, { colour: string; alpha: number; path: Path2D }>();
      for (const link of links) {
        const a = link.source as Node;
        const b = link.target as Node;
        const on = Boolean(over && (a === over || b === over));
        const alpha = on ? 0.95 : dim(a) && dim(b) ? 0.06 : dim(a) || dim(b) ? 0.12 : 0.4;
        const colour = on ? accent : colourOf.get(a.id)!;
        const key = `${colour}|${alpha}`;
        let group = strokes.get(key);
        if (!group) strokes.set(key, (group = { colour, alpha, path: new Path2D() }));
        group.path.moveTo(a.x!, a.y!);
        group.path.lineTo(b.x!, b.y!);
      }
      context.lineCap = "round";
      context.lineWidth = 1 / Math.sqrt(k);
      for (const { colour, alpha, path } of strokes.values()) {
        context.globalAlpha = alpha;
        context.strokeStyle = colour;
        context.stroke(path);
      }

      const dots = new Map<string, { colour: string; alpha: number; path: Path2D }>();
      for (const node of nodes) {
        const hot = node.id === focus || node === over;
        const colour = hot ? accent : colourOf.get(node.id)!;
        const faded = dim(node);
        if (glow && !faded) {
          const reach = (hot ? node.r + 2 : node.r) * 3.2;
          context.globalAlpha = 1;
          context.drawImage(halo(colour), node.x! - reach, node.y! - reach, reach * 2, reach * 2);
        }
        const alpha = faded ? 0.18 : 1;
        const key = `${colour}|${alpha}`;
        let group = dots.get(key);
        if (!group) dots.set(key, (group = { colour, alpha, path: new Path2D() }));
        const r = hot ? node.r + 2 : node.r;
        group.path.moveTo(node.x! + r, node.y!);
        group.path.arc(node.x!, node.y!, r, 0, Math.PI * 2);
      }
      for (const { colour, alpha, path } of dots.values()) {
        context.globalAlpha = alpha;
        context.fillStyle = colour;
        context.fill(path);
      }

      if (compact && nodes.length < 25) {
        context.textAlign = "center";
        context.textBaseline = "top";
        context.fillStyle = fg;
        context.font = `400 ${11 / k}px ${font}`;
        for (const node of nodes) {
          if (dim(node)) continue;
          context.globalAlpha = node.id === focus ? 1 : 0.8;
          const label = node.title.length > 32 ? `${node.title.slice(0, 30)}…` : node.title;
          context.fillText(label, node.x!, node.y! + node.r + 3 / k);
        }
      }
      context.globalAlpha = 1;
    };
    draw.current = paint;

    let touched = false;
    const fit = () => {
      if (touched || nodes.length === 0) return;
      const xs = nodes.map((n) => n.x!);
      const ys = nodes.map((n) => n.y!);
      const w = Math.max(...xs) - Math.min(...xs) + 60;
      const h = Math.max(...ys) - Math.min(...ys) + 60;
      const k = Math.min(3, Math.max(0.15, Math.min(element.clientWidth / w, element.clientHeight / h)));
      state.current.k = k;
      state.current.x = -((Math.max(...xs) + Math.min(...xs)) / 2) * k;
      state.current.y = -((Math.max(...ys) + Math.min(...ys)) / 2) * k;
    };
    element.addEventListener("pointerdown", () => (touched = true), { once: true });
    element.addEventListener("wheel", () => (touched = true), { once: true });
    const simulation = forceSimulation(nodes)
      .alphaDecay(0.045)
      .force("link", forceLink(links).distance(compact ? 55 : 80).strength(0.3))
      .force("charge", forceManyBody().strength(compact ? -160 : -220).theta(0.9))
      .force("center", forceCenter(0, 0))
      .force("x", forceX<Node>(0).strength(0.04 * Math.max(1, element.clientHeight / Math.max(1, element.clientWidth))))
      .force("y", forceY<Node>(0).strength(0.04 * Math.max(1, element.clientWidth / Math.max(1, element.clientHeight))))
      .force("collide", forceCollide<Node>().radius((n) => n.r + 3))
      .on("tick", () => {
        fit();
        paint();
      });
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      simulation.stop();
      simulation.tick(300);
      fit();
      paint();
    }

    const resize = new ResizeObserver(paint);
    resize.observe(element);
    return () => {
      simulation.stop();
      resize.disconnect();
    };
  }, [graph, focus, compact]);

  React.useEffect(() => draw.current(), [highlight]);

  React.useEffect(() => {
    const element = canvas.current!;
    const pointers = new Map<number, { x: number; y: number }>();
    let moved = 0;
    let pinch = 0;

    const toGraph = (clientX: number, clientY: number) => {
      const box = element.getBoundingClientRect();
      const { x, y, k } = state.current;
      return { gx: (clientX - box.left - box.width / 2 - x) / k, gy: (clientY - box.top - box.height / 2 - y) / k };
    };
    const hit = (clientX: number, clientY: number) => {
      const { gx, gy } = toGraph(clientX, clientY);
      let best: Node | null = null;
      let distance = Infinity;
      for (const node of state.current.nodes) {
        const d = Math.hypot(node.x! - gx, node.y! - gy);
        if (d < node.r + 6 / state.current.k && d < distance) {
          best = node;
          distance = d;
        }
      }
      return best;
    };

    const down = (event: PointerEvent) => {
      element.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      moved = 0;
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a!.x - b!.x, a!.y - b!.y);
      }
    };
    const move = (event: PointerEvent) => {
      const before = pointers.get(event.pointerId);
      if (!before) {
        const over = hit(event.clientX, event.clientY);
        if (over !== state.current.hover) {
          state.current.hover = over;
          setHover(over);
          element.style.cursor = over ? "pointer" : "grab";
          draw.current();
        }
        return;
      }
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        const span = Math.hypot(a!.x - b!.x, a!.y - b!.y);
        if (pinch) state.current.k = Math.min(6, Math.max(0.15, state.current.k * (span / pinch)));
        pinch = span;
      } else {
        state.current.x += event.clientX - before.x;
        state.current.y += event.clientY - before.y;
      }
      moved += Math.abs(event.clientX - before.x) + Math.abs(event.clientY - before.y);
      draw.current();
    };
    const up = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinch = 0;
      if (moved < 6) {
        const node = hit(event.clientX, event.clientY);
        if (node) openRef.current(node.id);
      }
    };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const box = element.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * 0.0015);
      const current = state.current;
      const k = Math.min(6, Math.max(0.15, current.k * factor));
      const px = event.clientX - box.left - box.width / 2;
      const py = event.clientY - box.top - box.height / 2;
      current.x = px - ((px - current.x) * k) / current.k;
      current.y = py - ((py - current.y) * k) / current.k;
      current.k = k;
      draw.current();
    };
    element.addEventListener("pointerdown", down);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", up);
    element.addEventListener("wheel", wheel, { passive: false });
    return () => {
      element.removeEventListener("pointerdown", down);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", up);
      element.removeEventListener("wheel", wheel);
    };
  }, []);

  return (
    <div className="mn-graph" data-compact={compact || undefined}>
      <canvas ref={canvas} className="mn-graph-canvas" role="img" aria-label={`Grafo de ${graph.nodes.length} notas y ${graph.edges.length} enlaces`} />
      {hover && !compact && (
        <p className="mn-graph-hover">
          {hover.title}
          {hover.folder && <span> · {hover.folder}</span>}
        </p>
      )}
    </div>
  );
}
