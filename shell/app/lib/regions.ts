type Entry = readonly [code: string, en: string, es: string];

const CATALOG: Record<string, readonly Entry[]> = {
  ES: [
    ["ES-AN", "Andalusia", "Andalucía"],
    ["ES-AR", "Aragon", "Aragón"],
    ["ES-AS", "Asturias", "Asturias"],
    ["ES-IB", "Balearic Islands", "Islas Baleares"],
    ["ES-PV", "Basque Country", "País Vasco"],
    ["ES-CN", "Canary Islands", "Canarias"],
    ["ES-CB", "Cantabria", "Cantabria"],
    ["ES-CL", "Castile and León", "Castilla y León"],
    ["ES-CM", "Castilla-La Mancha", "Castilla-La Mancha"],
    ["ES-CT", "Catalonia", "Cataluña"],
    ["ES-CE", "Ceuta", "Ceuta"],
    ["ES-EX", "Extremadura", "Extremadura"],
    ["ES-GA", "Galicia", "Galicia"],
    ["ES-RI", "La Rioja", "La Rioja"],
    ["ES-MD", "Madrid", "Comunidad de Madrid"],
    ["ES-ML", "Melilla", "Melilla"],
    ["ES-MC", "Murcia", "Región de Murcia"],
    ["ES-NC", "Navarre", "Navarra"],
    ["ES-VC", "Valencian Community", "Comunidad Valenciana"],
  ],
  DE: [
    ["DE-BW", "Baden-Württemberg", "Baden-Wurtemberg"],
    ["DE-BY", "Bavaria", "Baviera"],
    ["DE-BE", "Berlin", "Berlín"],
    ["DE-BB", "Brandenburg", "Brandeburgo"],
    ["DE-HB", "Bremen", "Bremen"],
    ["DE-HH", "Hamburg", "Hamburgo"],
    ["DE-HE", "Hesse", "Hesse"],
    ["DE-MV", "Mecklenburg-Western Pomerania", "Mecklemburgo-Pomerania Occidental"],
    ["DE-NI", "Lower Saxony", "Baja Sajonia"],
    ["DE-NW", "North Rhine-Westphalia", "Renania del Norte-Westfalia"],
    ["DE-RP", "Rhineland-Palatinate", "Renania-Palatinado"],
    ["DE-SL", "Saarland", "Sarre"],
    ["DE-SN", "Saxony", "Sajonia"],
    ["DE-ST", "Saxony-Anhalt", "Sajonia-Anhalt"],
    ["DE-SH", "Schleswig-Holstein", "Schleswig-Holstein"],
    ["DE-TH", "Thuringia", "Turingia"],
  ],
  FR: [
    ["FR-ARA", "Auvergne-Rhône-Alpes", "Auvernia-Ródano-Alpes"],
    ["FR-BFC", "Burgundy-Franche-Comté", "Borgoña-Franco Condado"],
    ["FR-BRE", "Brittany", "Bretaña"],
    ["FR-CVL", "Centre-Val de Loire", "Centro-Valle del Loira"],
    ["FR-COR", "Corsica", "Córcega"],
    ["FR-GES", "Grand Est", "Gran Este"],
    ["FR-HDF", "Hauts-de-France", "Alta Francia"],
    ["FR-IDF", "Île-de-France", "Isla de Francia"],
    ["FR-NOR", "Normandy", "Normandía"],
    ["FR-NAQ", "Nouvelle-Aquitaine", "Nueva Aquitania"],
    ["FR-OCC", "Occitania", "Occitania"],
    ["FR-PDL", "Pays de la Loire", "País del Loira"],
    ["FR-PAC", "Provence-Alpes-Côte d'Azur", "Provenza-Alpes-Costa Azul"],
  ],
  IT: [
    ["IT-65", "Abruzzo", "Abruzos"],
    ["IT-23", "Aosta Valley", "Valle de Aosta"],
    ["IT-75", "Apulia", "Apulia"],
    ["IT-77", "Basilicata", "Basilicata"],
    ["IT-78", "Calabria", "Calabria"],
    ["IT-72", "Campania", "Campania"],
    ["IT-45", "Emilia-Romagna", "Emilia-Romaña"],
    ["IT-36", "Friuli Venezia Giulia", "Friuli-Venecia Julia"],
    ["IT-62", "Lazio", "Lacio"],
    ["IT-42", "Liguria", "Liguria"],
    ["IT-25", "Lombardy", "Lombardía"],
    ["IT-57", "Marche", "Marcas"],
    ["IT-67", "Molise", "Molise"],
    ["IT-21", "Piedmont", "Piamonte"],
    ["IT-88", "Sardinia", "Cerdeña"],
    ["IT-82", "Sicily", "Sicilia"],
    ["IT-32", "Trentino-South Tyrol", "Trentino-Alto Adigio"],
    ["IT-52", "Tuscany", "Toscana"],
    ["IT-55", "Umbria", "Umbría"],
    ["IT-34", "Veneto", "Véneto"],
  ],
  GB: [
    ["GB-ENG", "England", "Inglaterra"],
    ["GB-NIR", "Northern Ireland", "Irlanda del Norte"],
    ["GB-SCT", "Scotland", "Escocia"],
    ["GB-WLS", "Wales", "Gales"],
  ],
  BE: [
    ["BE-BRU", "Brussels", "Bruselas"],
    ["BE-VLG", "Flanders", "Flandes"],
    ["BE-WAL", "Wallonia", "Valonia"],
  ],
  AT: [
    ["AT-1", "Burgenland", "Burgenland"],
    ["AT-2", "Carinthia", "Carintia"],
    ["AT-3", "Lower Austria", "Baja Austria"],
    ["AT-4", "Upper Austria", "Alta Austria"],
    ["AT-5", "Salzburg", "Salzburgo"],
    ["AT-6", "Styria", "Estiria"],
    ["AT-7", "Tyrol", "Tirol"],
    ["AT-9", "Vienna", "Viena"],
    ["AT-8", "Vorarlberg", "Vorarlberg"],
  ],
};

export interface RegionOption {
  code: string;
  name: string;
}

export function hasRegions(country: string | null): boolean {
  return country !== null && country in CATALOG;
}

export function regionsOf(country: string | null, locale: string): RegionOption[] {
  const found = country ? (CATALOG[country] ?? []) : [];
  return found
    .map(([code, en, es]) => ({ code, name: locale === "es" ? es : en }))
    .sort((a, b) => a.name.localeCompare(b.name, locale));
}

export function regionName(code: string | null, locale: string): string | null {
  if (!code) return null;
  const country = code.split("-")[0] ?? "";
  return regionsOf(country, locale).find((one) => one.code === code)?.name ?? null;
}
