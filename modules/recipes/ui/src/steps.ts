export const ACTIONS: Record<string, string> = {
  wash: "Lavar",
  peel: "Pelar",
  chop: "Picar",
  mix: "Mezclar",
  knead: "Amasar",
  season: "Salpimentar",
  coat: "Rebozar",
  fry: "Freír",
  saute: "Pochar",
  boil: "Hervir",
  simmer: "Cocer a fuego lento",
  steam: "Cocer al vapor",
  bake: "Hornear",
  roast: "Asar",
  grill: "A la plancha",
  toast: "Tostar",
  rest: "Reposar",
  marinate: "Marinar",
  chill: "Enfriar",
  freeze: "Congelar",
  prove: "Fermentar",
  blend: "Triturar",
  strain: "Escurrir",
  assemble: "Montar",
  serve: "Servir",
};

export const EQUIPMENT: Record<string, string> = {
  hob: "Fuego",
  oven: "Horno",
  air_fryer: "Freidora de aire",
  board: "Tabla",
  bowl: "Bol",
  fridge: "Nevera",
  none: "Sin nada",
};

export const USUALLY_UNATTENDED = new Set([
  "bake",
  "roast",
  "rest",
  "marinate",
  "chill",
  "freeze",
  "prove",
  "simmer",
]);

export function whenLabel(start: number, end: number): string {
  return start === end ? `min ${start}` : `min ${start} a ${end}`;
}
