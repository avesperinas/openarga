#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const OUT = join(ROOT, "modules/outings/ui/public/map");
const PMTILES = "protomaps/go-pmtiles:v1.31.2";
const GDAL = "ghcr.io/osgeo/gdal:ubuntu-small-3.11.0";
const MAPSHAPER = ["-y", "mapshaper@0.7.67"];
const WCS = "https://servicios.idee.es/wcs-inspire/mdt";
const FONTS = "https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts";
const USER = `${process.getuid()}:${process.getgid()}`;

const NAVARRA = { name: "navarra", box: [-2.55, 41.9, -0.7, 43.35], maxzoom: 9, coverage: "Elevacion4258_200", every: 100 };
const COMARCA = { name: "comarca", box: [-1.82, 42.7, -1.47, 42.93], maxzoom: 14, coverage: "Elevacion4258_25", every: 40 };
const FACES = ["Noto Sans Regular", "Noto Sans Medium", "Noto Sans Italic"];
const RANGES = ["0-255", "256-511", "8192-8447"];

function run(command, args, options = {}) {
  return execFileSync(command, args, { stdio: ["ignore", "pipe", "inherit"], ...options });
}

function build() {
  const asked = process.argv[2];
  if (asked) return `${asked}.pmtiles`;
  const builds = JSON.parse(run("curl", ["-sSLf", "https://build-metadata.protomaps.dev/builds.json"]).toString());
  return builds.at(-1).key;
}

mkdirSync(OUT, { recursive: true });
const work = mkdtempSync(join(tmpdir(), "arga-area-map-"));
const source = `https://build.protomaps.com/${build()}`;

for (const piece of [NAVARRA, COMARCA]) {
  run("docker", [
    "run", "--rm", "--user", USER, "-v", `${OUT}:/out`, PMTILES,
    "extract", source, `/out/${piece.name}.pmtiles`,
    `--bbox=${piece.box.join(",")}`, `--maxzoom=${piece.maxzoom}`,
  ]);

  const [west, south, east, north] = piece.box;
  const tif = join(work, `${piece.name}.tif`);
  run("curl", [
    "-sSLf", "-o", tif,
    `${WCS}?SERVICE=WCS&REQUEST=GetCoverage&VERSION=2.0.1&COVERAGEID=${piece.coverage}` +
      `&SUBSET=Lat(${south},${north})&SUBSET=Long(${west},${east})&FORMAT=image/tiff`,
  ]);
  run("docker", [
    "run", "--rm", "--user", USER, "-v", `${work}:/w`, "-w", "/w", GDAL,
    "gdal_contour", "-a", "ele", "-i", String(piece.every), `${piece.name}.tif`, `${piece.name}.geojson`,
  ]);
  run("npx", [
    ...MAPSHAPER, join(work, `${piece.name}.geojson`),
    "-filter", "ele > 0",
    "-simplify", "8%", "keep-shapes",
    "-filter-fields", "ele",
    "-rename-layers", "relief",
    "-o", "format=topojson", "quantization=100000", join(OUT, `relieve-${piece.name}.json`),
  ]);
}

for (const face of FACES) {
  const folder = join(OUT, "fonts", face);
  mkdirSync(folder, { recursive: true });
  for (const range of RANGES) {
    run("curl", ["-sSLf", "-o", join(folder, `${range}.pbf`), `${FONTS}/${encodeURIComponent(face)}/${range}.pbf`]);
  }
}

const made = { source, built: new Date().toISOString().slice(0, 10), files: {} };
for (const name of ["navarra.pmtiles", "comarca.pmtiles", "relieve-navarra.json", "relieve-comarca.json"]) {
  made.files[name] = statSync(join(OUT, name)).size;
}
writeFileSync(join(OUT, "build.json"), `${JSON.stringify(made, null, 2)}\n`);
for (const [name, size] of Object.entries(made.files)) {
  console.log(`${name.padEnd(24)} ${(size / 1e6).toFixed(1)} MB`);
}
