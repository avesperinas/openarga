import en from "../i18n/en.json";
import es from "../i18n/es.json";

const NAMES: Record<string, Record<string, string>> = { en, es };
const ENGLISH: Record<string, string> = en;

const CODES: Record<string, readonly string[]> = {
  ES: ["ES-AN", "ES-AR", "ES-AS", "ES-IB", "ES-PV", "ES-CN", "ES-CB", "ES-CL", "ES-CM", "ES-CT", "ES-CE", "ES-EX", "ES-GA", "ES-RI", "ES-MD", "ES-ML", "ES-MC", "ES-NC", "ES-VC"],
  DE: ["DE-BW", "DE-BY", "DE-BE", "DE-BB", "DE-HB", "DE-HH", "DE-HE", "DE-MV", "DE-NI", "DE-NW", "DE-RP", "DE-SL", "DE-SN", "DE-ST", "DE-SH", "DE-TH"],
  FR: ["FR-ARA", "FR-BFC", "FR-BRE", "FR-CVL", "FR-COR", "FR-GES", "FR-HDF", "FR-IDF", "FR-NOR", "FR-NAQ", "FR-OCC", "FR-PDL", "FR-PAC"],
  IT: ["IT-65", "IT-23", "IT-75", "IT-77", "IT-78", "IT-72", "IT-45", "IT-36", "IT-62", "IT-42", "IT-25", "IT-57", "IT-67", "IT-21", "IT-88", "IT-82", "IT-32", "IT-52", "IT-55", "IT-34"],
  GB: ["GB-ENG", "GB-NIR", "GB-SCT", "GB-WLS"],
  BE: ["BE-BRU", "BE-VLG", "BE-WAL"],
  AT: ["AT-1", "AT-2", "AT-3", "AT-4", "AT-5", "AT-6", "AT-7", "AT-9", "AT-8"],
};

export interface RegionOption {
  code: string;
  name: string;
}

export function hasRegions(country: string | null): boolean {
  return country !== null && country in CODES;
}

export function regionsOf(country: string | null, locale: string): RegionOption[] {
  const found = country ? (CODES[country] ?? []) : [];
  const names = NAMES[locale] ?? ENGLISH;
  return found
    .map((code) => ({ code, name: names[`region.${code}`] ?? ENGLISH[`region.${code}`] ?? code }))
    .sort((a, b) => a.name.localeCompare(b.name, locale));
}

export function regionName(code: string | null, locale: string): string | null {
  if (!code) return null;
  const country = code.split("-")[0] ?? "";
  return regionsOf(country, locale).find((one) => one.code === code)?.name ?? null;
}
