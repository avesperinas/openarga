#!/usr/bin/env node

import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { COLLECTION, measure } from "../packages/ui/wallpapers.mjs";

const ROOT = new URL("..", import.meta.url).pathname;
const IMAGES = join(ROOT, "shell/public/wallpapers");
const MANIFEST = join(ROOT, "packages/ui/wallpapers.json");

const SIDE = 1000;
const BLUR = 60;

const svg = (wallpaper, blurred) => {
  const gradients = wallpaper.blobs
    .map(
      (blob, index) => `
    <radialGradient id="b${index}" cx="${blob.cx}" cy="${blob.cy}" r="${blob.r}">
      <stop offset="0" stop-color="${blob.color}" stop-opacity="${blob.alpha}"/>
      <stop offset="1" stop-color="${blob.color}" stop-opacity="0"/>
    </radialGradient>`,
    )
    .join("");
  const rects = wallpaper.blobs
    .map((_, index) => `    <rect width="${SIDE}" height="${SIDE}" fill="url(#b${index})"/>`)
    .join("\n");

  const filter = blurred
    ? `
    <filter id="desenfoque" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="${BLUR}"/>
    </filter>`
    : "";

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SIDE} ${SIDE}" preserveAspectRatio="xMidYMid slice">
  <defs>${gradients}${filter}
  </defs>
  <g${blurred ? ' filter="url(#desenfoque)"' : ""}>
    <rect width="${SIDE}" height="${SIDE}" fill="${wallpaper.base}"/>
${rects}
  </g>
</svg>
`;
};

const build = () => {
  const files = new Map();
  const manifest = [];

  for (const wallpaper of COLLECTION) {
    const measured = measure(wallpaper);
    files.set(`${wallpaper.id}.svg`, svg(wallpaper, false));
    files.set(`${wallpaper.id}-blur.svg`, svg(wallpaper, true));
    manifest.push({
      ...measured,
      image: `/wallpapers/${wallpaper.id}.svg`,
      blurred: `/wallpapers/${wallpaper.id}-blur.svg`,
    });
  }

  return { files, manifest: JSON.stringify(manifest, null, 2) + "\n" };
};

const { files, manifest } = build();
const checking = process.argv.includes("--check");

if (checking) {
  const stale = [];
  let onDisk;
  try {
    onDisk = new Set(readdirSync(IMAGES));
  } catch {
    stale.push("falta shell/public/wallpapers");
    onDisk = new Set();
  }
  for (const [name, content] of files) {
    if (!onDisk.has(name)) stale.push(`falta ${name}`);
    else if (readFileSync(join(IMAGES, name), "utf8") !== content) stale.push(`cambió ${name}`);
  }
  for (const name of onDisk) if (!files.has(name)) stale.push(`sobra ${name}`);
  if (readFileSync(MANIFEST, "utf8") !== manifest) stale.push("cambió wallpapers.json");

  if (stale.length) {
    console.error(`fondos desfasados: ${stale.join(", ")}. Corre \`node scripts/make-wallpapers.mjs\`.`);
    process.exit(1);
  }
  console.log(`fondos ok · ${COLLECTION.length} fondo(s), velo calculado y al día`);
} else {
  mkdirSync(IMAGES, { recursive: true });
  for (const [name, content] of files) writeFileSync(join(IMAGES, name), content);
  writeFileSync(MANIFEST, manifest);
  console.log(`fondos escritos · ${COLLECTION.length} fondo(s) en shell/public/wallpapers`);
}
