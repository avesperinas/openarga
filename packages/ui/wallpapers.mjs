export const FLOOR = 4.5;

export const MUTED_FLOOR = 3.0;

export const VEIL_MAX = 0.35;

export const GRID = 64;

export const THEMES = {
  light: { fg: "#10131a", muted: "#5b6272", scrim: "#eef1f6", glass: "#ffffff" },
  dark: { fg: "#f2f4f8", muted: "#a2aabb", scrim: "#0b0e14", glass: "#161c2a" },
};

export const COLLECTION = [
  {
    id: "marea",
    name: "Marea",
    base: "#2a3f5f",
    blobs: [
      { cx: 0.15, cy: 0.1, r: 0.75, color: "#4a7ba7", alpha: 0.85 },
      { cx: 0.85, cy: 0.35, r: 0.6, color: "#1d2b45", alpha: 0.7 },
      { cx: 0.5, cy: 0.95, r: 0.65, color: "#3d6389", alpha: 0.55 },
      { cx: 0.25, cy: 0.7, r: 0.3, color: "#5b90bd", alpha: 0.4 },
    ],
  },
  {
    id: "brezo",
    name: "Brezo",
    base: "#4a3a56",
    blobs: [
      { cx: 0.8, cy: 0.15, r: 0.7, color: "#6d5480", alpha: 0.8 },
      { cx: 0.1, cy: 0.6, r: 0.65, color: "#33283d", alpha: 0.75 },
      { cx: 0.6, cy: 0.85, r: 0.5, color: "#7a5f8e", alpha: 0.45 },
      { cx: 0.4, cy: 0.3, r: 0.28, color: "#8b6fa0", alpha: 0.35 },
    ],
  },
  {
    id: "duna",
    name: "Duna",
    base: "#6b5a44",
    blobs: [
      { cx: 0.2, cy: 0.2, r: 0.8, color: "#8d7859", alpha: 0.8 },
      { cx: 0.9, cy: 0.7, r: 0.6, color: "#4e4132", alpha: 0.8 },
      { cx: 0.45, cy: 0.55, r: 0.35, color: "#a08b68", alpha: 0.45 },
    ],
  },
  {
    id: "pizarra",
    name: "Pizarra",
    base: "#3d4148",
    blobs: [
      { cx: 0.7, cy: 0.2, r: 0.75, color: "#565b64", alpha: 0.85 },
      { cx: 0.15, cy: 0.8, r: 0.7, color: "#2a2d33", alpha: 0.8 },
      { cx: 0.5, cy: 0.45, r: 0.3, color: "#656b76", alpha: 0.4 },
    ],
  },
];

export const rgb = (hex) => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
];

export function luminance([r, g, b]) {
  const channel = (value) => {
    const v = value / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const over = (source, backdrop, alpha) =>
  backdrop.map((value, index) => source[index] * alpha + value * (1 - alpha));

export function pixel(wallpaper, x, y) {
  let colour = rgb(wallpaper.base);
  for (const blob of wallpaper.blobs) {
    const distance = Math.hypot(x - blob.cx, y - blob.cy) / blob.r;
    if (distance >= 1) continue;
    colour = over(rgb(blob.color), colour, blob.alpha * (1 - distance));
  }
  return colour;
}

export function samples(wallpaper, grid = GRID) {
  const points = [];
  for (let row = 0; row < grid; row++) {
    for (let column = 0; column < grid; column++) {
      points.push(pixel(wallpaper, (column + 0.5) / grid, (row + 0.5) / grid));
    }
  }
  return points;
}

function weakest(front, points, tint, alpha, floor) {
  let worst = Infinity;
  for (const point of points) {
    const mixed = luminance(over(tint, point, alpha));
    const [high, low] = front > mixed ? [front, mixed] : [mixed, front];
    const value = (high + 0.05) / (low + 0.05);
    if (value < worst) {
      worst = value;
      if (worst < floor) return worst;
    }
  }
  return worst;
}

export function alphaFor(points, tint, needs) {
  const colour = rgb(tint);
  const fronts = needs.map(([fg, floor]) => [luminance(rgb(fg)), floor]);
  let worst = 0;
  for (let step = 0; step <= 100; step++) {
    const alpha = step / 100;
    const results = fronts.map(([front, floor]) => weakest(front, points, colour, alpha, floor));
    worst = results[0];
    if (results.every((value, index) => value >= fronts[index][1])) return { alpha, worst };
  }
  return { alpha: 1, worst };
}

export const scrimFor = (wallpaper, theme, floor = FLOOR) =>
  alphaFor(samples(wallpaper), THEMES[theme].scrim, [[THEMES[theme].fg, floor]]);

export function statistics(wallpaper) {
  const values = samples(wallpaper).map(luminance);
  const mean = values.reduce((total, value) => total + value, 0) / values.length;
  const variance =
    values.reduce((total, value) => total + (value - mean) ** 2, 0) / values.length;
  return { mean, variance, max: Math.max(...values), min: Math.min(...values) };
}

export function measure(wallpaper) {
  const stats = statistics(wallpaper);
  const points = samples(wallpaper);
  const themes = Object.keys(THEMES);
  const scrims = Object.fromEntries(
    themes.map((theme) => [theme, alphaFor(points, THEMES[theme].scrim, [[THEMES[theme].fg, FLOOR]])]),
  );
  const glass = Object.fromEntries(
    themes.map((theme) => [
      theme,
      alphaFor(points, THEMES[theme].glass, [
        [THEMES[theme].fg, FLOOR],
        [THEMES[theme].muted, MUTED_FLOOR],
      ]),
    ]),
  );
  return {
    id: wallpaper.id,
    name: wallpaper.name,
    luminance: { mean: +stats.mean.toFixed(4), variance: +stats.variance.toFixed(5) },
    scrim: { light: scrims.light.alpha, dark: scrims.dark.alpha },
    veil: {
      light: Math.min(scrims.light.alpha, VEIL_MAX),
      dark: Math.min(scrims.dark.alpha, VEIL_MAX),
    },
    glass: { light: glass.light.alpha, dark: glass.dark.alpha },
    contrast: {
      light: +scrims.light.worst.toFixed(2),
      dark: +scrims.dark.worst.toFixed(2),
    },
  };
}
