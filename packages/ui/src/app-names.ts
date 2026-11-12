export type AppNameSet = "standard" | "arga" | "greek" | "custom";

export const APP_NAME_SETS: { value: AppNameSet; label: string }[] = [
  { value: "standard", label: "Standard" },
  { value: "arga", label: "Arga" },
  { value: "greek", label: "Greek gods" },
  { value: "custom", label: "Your own" },
];

export const APP_NAME_MAX = 24;

export const APP_NAMES: Record<Exclude<AppNameSet, "standard" | "custom">, Record<string, string>> = {
  arga: {
    training: "Redín",
    vitals: "Pulso",
    macros: "Macros",
    shopping: "Mercado",
    money: "Comptos",
    outings: "Dionisio",
    travel: "Elcano",
    library: "Liburu",
    planner: "Cronos",
    notebook: "Mnemo",
    insights: "Misi",
    goals: "Recado",
    study: "Aula",
    hub: "Conectores",
  },
  greek: {
    training: "Heracles",
    vitals: "Asclepius",
    macros: "Demeter",
    recipes: "Hestia",
    shopping: "Hermes",
    money: "Plutus",
    goals: "Nike",
    study: "Athena",
    library: "Apollo",
    travel: "Poseidon",
    notebook: "Mnemosyne",
    hub: "Iris",
    planner: "Chronos",
    outings: "Dionysus",
    insights: "Metis",
  },
};

export interface AppNamePreferences {
  app_names?: AppNameSet;
  custom_app_names?: Record<string, string>;
}

export function appNameOf(id: string, standard: string, preferences?: AppNamePreferences | null): string {
  const set = preferences?.app_names ?? "standard";
  if (set === "standard") return standard;
  if (set === "custom") return preferences?.custom_app_names?.[id]?.trim() || standard;
  return APP_NAMES[set]?.[id] ?? standard;
}
