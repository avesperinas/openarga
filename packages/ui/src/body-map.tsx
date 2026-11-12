import * as React from "react";

import { BODY_BACK, BODY_FRONT, type BodyZone } from "./body-map-paths";

export type BodySide = "front" | "back";

export const BODY_MUSCLES = [
  "chest",
  "front_delts",
  "side_delts",
  "rear_delts",
  "lats",
  "upper_back",
  "biceps",
  "triceps",
  "forearms",
  "abs",
  "lower_back",
  "quads",
  "hamstrings",
  "glutes",
  "calves",
  "adductors",
] as const;
export type BodyMuscle = (typeof BODY_MUSCLES)[number];

const ZONES: Record<BodySide, Record<string, BodyMuscle[]>> = {
  front: {
    chest: ["chest"],
    deltoids: ["front_delts", "side_delts"],
    biceps: ["biceps"],
    triceps: ["triceps"],
    forearm: ["forearms"],
    abs: ["abs"],
    obliques: ["abs"],
    trapezius: ["upper_back"],
    quadriceps: ["quads"],
    adductors: ["adductors"],
    calves: ["calves"],
    tibialis: ["calves"],
  },
  back: {
    deltoids: ["rear_delts", "side_delts"],
    trapezius: ["upper_back"],
    "upper-back": ["lats"],
    "lower-back": ["lower_back"],
    triceps: ["triceps"],
    forearm: ["forearms"],
    gluteal: ["glutes"],
    hamstring: ["hamstrings"],
    adductors: ["adductors"],
    calves: ["calves"],
  },
};

const DRAWING: Record<BodySide, { zones: BodyZone[]; viewBox: string }> = {
  front: { zones: BODY_FRONT, viewBox: "0 0 724 1448" },
  back: { zones: BODY_BACK, viewBox: "724 0 724 1448" },
};

export const musclesOn = (side: BodySide): BodyMuscle[] => [...new Set(Object.values(ZONES[side]).flat())];

export function muscleOfZone(side: BodySide, zone: string, colors: Partial<Record<string, string>>) {
  const muscles = ZONES[side][zone];
  if (!muscles) return null;
  return muscles.find((muscle) => colors[muscle]) ?? muscles[0]!;
}

export interface BodyMapProps {
  side: BodySide;
  colors: Partial<Record<string, string>>;
  label: string;
  names?: Partial<Record<string, string>>;
  onSelect?: (muscle: BodyMuscle) => void;
}

export function BodyMap({ side, colors, label, names = {}, onSelect }: BodyMapProps) {
  const { zones, viewBox } = DRAWING[side];
  return (
    <svg className="body-map" viewBox={viewBox} role={onSelect ? "group" : "img"} aria-label={label}>
      {zones.map((zone) => {
        const muscle = muscleOfZone(side, zone.zone, colors);
        const fill = muscle ? colors[muscle] ?? "var(--body-empty)" : "var(--body-base)";
        const paths = zone.paths.map((d, index) => <path key={index} d={d} fill={fill} />);
        if (!muscle || !onSelect) {
          return (
            <g key={zone.zone} className="body-map-zone" data-muscle={muscle ?? undefined}>
              {muscle && names[muscle] && <title>{names[muscle]}</title>}
              {paths}
            </g>
          );
        }
        return (
          <g
            key={zone.zone}
            className="body-map-zone"
            data-muscle={muscle}
            data-selectable=""
            role="button"
            tabIndex={0}
            aria-label={names[muscle] ?? muscle}
            onClick={() => onSelect(muscle)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(muscle);
              }
            }}
          >
            {paths}
          </g>
        );
      })}
    </svg>
  );
}

export function BodyMaps({
  colors,
  label,
  names,
  onSelect,
  compact = false,
}: Omit<BodyMapProps, "side"> & { compact?: boolean }) {
  return (
    <div className="body-maps" data-size={compact ? "compact" : undefined}>
      {(["front", "back"] as const).map((side) => (
        <figure key={side} className="body-maps-side">
          <BodyMap
            side={side}
            colors={colors}
            label={`${label}, ${side === "front" ? "de frente" : "de espalda"}`}
            names={names}
            onSelect={onSelect}
          />
          <figcaption>{side === "front" ? "Frente" : "Espalda"}</figcaption>
        </figure>
      ))}
    </div>
  );
}

export function changeColor(delta: number | null | undefined): string | undefined {
  if (delta === null || delta === undefined) return undefined;
  if (Math.abs(delta) <= 1) return "var(--body-steady)";
  const strength = Math.round(35 + Math.min(Math.abs(delta), 10) * 6.5);
  const tone = delta > 0 ? "var(--positive)" : "var(--negative)";
  return `color-mix(in srgb, ${tone} ${strength}%, var(--body-steady))`;
}

export function amountColor(amount: number, tone = "var(--accent)"): string | undefined {
  if (amount <= 0) return undefined;
  const strength = Math.round(25 + Math.min(amount, 1) * 75);
  return `color-mix(in srgb, ${tone} ${strength}%, var(--body-steady))`;
}
