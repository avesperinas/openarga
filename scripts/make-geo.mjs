#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const OUT = join(ROOT, "packages/ui/geo");
const NE = "https://naciscdn.org/naturalearth/10m/cultural";
const MAPSHAPER = ["-y", "mapshaper@0.7.67"];

const work = mkdtempSync(join(tmpdir(), "arga-geo-"));
for (const name of ["ne_10m_admin_0_countries", "ne_10m_admin_1_states_provinces"]) {
  execFileSync("curl", ["-sSLf", "-o", join(work, `${name}.zip`), `${NE}/${name}.zip`]);
  execFileSync("unzip", ["-oq", join(work, `${name}.zip`), "-d", work]);
}

const NAMES = JSON.parse(readFileSync(join(OUT, "names.json"), "utf8"));
const SPAIN = NAMES.spain;
const BELGIUM = NAMES.belgium;
const BRITAIN = NAMES.britain;
const ITALY = NAMES.italy;

function regionOf(p) {
  const clean = (value) => String(value ?? "").trim();
  if (p.adm0_a3 === "ESP") {
    if (p.name === "Ceuta") return ["ES-CE", "Ceuta"];
    if (p.name === "Melilla") return ["ES-ML", "Melilla"];
    return SPAIN[clean(p.region_cod).replace("ES.", "")];
  }
  if (p.adm0_a3 === "FRA" && clean(p.region_cod)) return [clean(p.region_cod), clean(p.region)];
  if (p.adm0_a3 === "ITA" && clean(p.region_cod)) {
    return [clean(p.region_cod), ITALY[clean(p.region)] ?? clean(p.region)];
  }
  if (p.adm0_a3 === "BEL") return BELGIUM[clean(p.region)];
  if (p.adm0_a3 === "GBR") return BRITAIN[clean(p.geonunit)];
  return undefined;
}

const table = {};
{
  const dbf = join(work, "attributes.json");
  execFileSync("npx", [
    ...MAPSHAPER,
    join(work, "ne_10m_admin_1_states_provinces.shp"),
    "-filter-fields", "adm1_code,adm0_a3,iso_a2,iso_3166_2,name,name_es,region,region_cod,geonunit",
    "-o", "format=json", dbf,
  ], { stdio: ["ignore", "ignore", "inherit"] });
  for (const p of JSON.parse(readFileSync(dbf, "utf8"))) {
    const grouped = regionOf(p);
    const iso = String(p.iso_3166_2 ?? "").trim();
    const code = grouped?.[0] ?? (iso && !iso.includes("-99") ? iso : p.adm1_code);
    const name = grouped?.[1] ?? (String(p.name_es ?? "").trim() || p.name);
    table[p.adm1_code] = { code, name, country: p.iso_a2 };
  }
  writeFileSync(join(work, "regions.cjs"), `module.exports = ${JSON.stringify(table)};`);
}

mkdirSync(OUT, { recursive: true });

execFileSync("npx", [
  ...MAPSHAPER,
  join(work, "ne_10m_admin_0_countries.shp"),
  "-filter", 'ISO_A2_EH != "-99" && ISO_A2_EH != "AQ"',
  "-each", "code = ISO_A2_EH, name = NAME_ES || NAME",
  "-filter-fields", "code,name",
  "-dissolve", "code", "copy-fields=name",
  "-simplify", "10%", "weighted", "keep-shapes",
  "-rename-layers", "countries",
  "-o", "format=topojson", "quantization=1000000", join(OUT, "countries.json"),
], { stdio: ["ignore", "ignore", "inherit"] });

execFileSync("npx", [
  ...MAPSHAPER,
  join(work, "ne_10m_admin_1_states_provinces.shp"),
  "-filter", 'iso_a2 != "AQ" && iso_a2 != "-99"',
  "-require", join(work, "regions.cjs"), "alias=_t",
  "-each", "var r = _t[adm1_code]; code = r.code; name = r.name; country = r.country",
  "-filter-fields", "code,name,country",
  "-dissolve", "code", "copy-fields=name,country",
  "-simplify", "8%", "weighted", "keep-shapes",
  "-rename-layers", "regions",
  "-o", "format=topojson", "quantization=100000", join(OUT, "regions.json"),
], { stdio: ["ignore", "ignore", "inherit"] });

console.log(`geometries in ${OUT}`);
