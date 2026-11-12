#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const MODULE = new URL("..", import.meta.url).pathname;
const PMTILES = "protomaps/go-pmtiles:v1.31.2";
const GDAL = "ghcr.io/osgeo/gdal:ubuntu-small-3.11.0";
const MAPSHAPER = ["-y", "mapshaper@0.7.67"];
const FONTS = "https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts";
const FACES = ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"];
const RANGES = ["0-255", "256-511", "8192-8447"];
const USER = `${process.getuid()}:${process.getgid()}`;

function run(command, args, options = {}) {
  return execFileSync(command, args, { stdio: ["ignore", "pipe", "inherit"], ...options });
}

function profile(id) {
  const read = "import json, sys, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))))";
  return JSON.parse(run("uv", ["run", "--no-sync", "python", "-c", read, join(MODULE, "areas", `${id}.yaml`)]).toString());
}

function build(asked) {
  if (asked) return `${asked}.pmtiles`;
  const builds = JSON.parse(run("curl", ["-sSLf", "https://build-metadata.protomaps.dev/builds.json"]).toString());
  return builds.at(-1).key;
}

const [id, asked] = process.argv.slice(2);
if (!id) {
  console.error("usage: make-area-map.mjs <area id> [protomaps build]");
  process.exit(2);
}
const area = profile(id);
const MAP = join(MODULE, "ui/public/map");
const OUT = join(MAP, id);
mkdirSync(OUT, { recursive: true });
const work = mkdtempSync(join(tmpdir(), "arga-area-map-"));
const source = `https://build.protomaps.com/${build(asked)}`;
const files = [];

for (const name of ["region", "near"]) {
  const piece = area.map[name];
  run("docker", [
    "run", "--rm", "--user", USER, "-v", `${OUT}:/out`, PMTILES,
    "extract", source, `/out/${name}.pmtiles`,
    `--bbox=${piece.box.join(",")}`, `--maxzoom=${piece.maxzoom}`,
  ]);
  files.push(`${name}.pmtiles`);

  const relief = area.map.relief;
  if (!relief) continue;
  const { coverage, every } = relief[name];
  const [west, south, east, north] = piece.box;
  const tif = join(work, `${name}.tif`);
  run("curl", [
    "-sSLf", "-o", tif,
    `${relief.wcs}?SERVICE=WCS&REQUEST=GetCoverage&VERSION=2.0.1&COVERAGEID=${coverage}` +
      `&SUBSET=Lat(${south},${north})&SUBSET=Long(${west},${east})&FORMAT=image/tiff`,
  ]);
  run("docker", [
    "run", "--rm", "--user", USER, "-v", `${work}:/w`, "-w", "/w", GDAL,
    "gdal_contour", "-a", "ele", "-i", String(every), `${name}.tif`, `${name}.geojson`,
  ]);
  run("npx", [
    ...MAPSHAPER, join(work, `${name}.geojson`),
    "-filter", "ele > 0",
    "-simplify", "8%", "keep-shapes",
    "-filter-fields", "ele",
    "-rename-layers", "relief",
    "-o", "format=topojson", "quantization=100000", join(OUT, `relief-${name}.json`),
  ]);
  files.push(`relief-${name}.json`);
}

for (const face of FACES) {
  const folder = join(MAP, "fonts", face);
  mkdirSync(folder, { recursive: true });
  for (const range of RANGES) {
    run("curl", ["-sSLf", "-o", join(folder, `${range}.pbf`), `${FONTS}/${encodeURIComponent(face)}/${range}.pbf`]);
  }
}

const made = { area: id, source, built: new Date().toISOString().slice(0, 10), files: {} };
for (const name of files) made.files[name] = statSync(join(OUT, name)).size;
writeFileSync(join(OUT, "build.json"), `${JSON.stringify(made, null, 2)}\n`);
for (const [name, size] of Object.entries(made.files)) {
  console.log(`${name.padEnd(24)} ${(size / 1e6).toFixed(1)} MB`);
}
