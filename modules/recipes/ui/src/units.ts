import type { Unit } from "./api";

export const UNITS: { value: Unit; label: string; short: string }[] = [
  { value: "g", label: "gramos", short: "g" },
  { value: "ml", label: "mililitros", short: "ml" },
  { value: "unit", label: "unidades", short: "ud" },
  { value: "tbsp", label: "cucharadas", short: "cda" },
  { value: "tsp", label: "cucharaditas", short: "cdta" },
  { value: "pinch", label: "pizcas", short: "pizca" },
];

const NUMBER = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 });

export function quantityLabel(quantity: number, unit: Unit): string {
  const found = UNITS.find((one) => one.value === unit);
  return `${NUMBER.format(quantity)} ${found?.short ?? unit}`;
}
