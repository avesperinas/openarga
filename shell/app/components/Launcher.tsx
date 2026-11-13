"use client";

import { EmptyState, type IconStyle, styledIcon, zonedDates } from "@openarga/ui";
import * as React from "react";

import { appIconOf } from "../lib/app-icons";
import type { ModuleSummary } from "../lib/kernel";

export const FAMILIES = [
  { id: "health", label: "Salud" },
  { id: "goals", label: "Objetivos" },
  { id: "growth", label: "Crecimiento" },
  { id: "wellbeing", label: "Bienestar" },
] as const;

export const FILLERS = ["finance", "system"] as const;

const byName = (a: ModuleSummary, b: ModuleSummary) => a.name.localeCompare(b.name, "es");

export function groupModules(modules: ModuleSummary[]) {
  const known = new Set<string>(["calendar", "companion", ...FILLERS, ...FAMILIES.map((family) => family.id)]);
  const of = (id: string) => modules.filter((module) => module.family === id).sort(byName);
  return {
    pinned: of("calendar"),
    companions: of("companion"),
    families: FAMILIES.map((family) => ({ ...family, modules: of(family.id) })).filter(
      (family) => family.modules.length > 0,
    ),
    fillers: [...FILLERS.flatMap((id) => of(id)), ...modules.filter((module) => !known.has(module.family ?? "")).sort(byName)],
  };
}

export const BLOCK = 4;

export function placeBlocks(main: ModuleSummary[][], fillers: ModuleSummary[]) {
  const blocks: ModuleSummary[][] = [];
  for (const family of main) {
    for (let start = 0; start < family.length; start += BLOCK) blocks.push(family.slice(start, start + BLOCK));
  }
  const rest = [...fillers];
  for (const block of blocks) {
    while (block.length < BLOCK && rest.length > 0) block.push(rest.shift()!);
  }
  while (rest.length > 0) blocks.push(rest.splice(0, BLOCK));

  const placed = new Map<string, { phone: [number, number]; desktop: [number, number] }>();
  blocks.forEach((block, index) =>
    block.forEach((module, slot) =>
      placed.set(module.id, {
        phone: [slot + 1, index + 1],
        desktop: [(index % 2) * BLOCK + slot + 1, Math.floor(index / 2) + 1],
      }),
    ),
  );
  return { order: blocks.flat(), placed };
}

function useUnseen(modules: ModuleSummary[]): Record<string, number> {
  const [unseen, setUnseen] = React.useState<Record<string, number>>({});
  const wanted = modules.some((module) => module.badge);
  React.useEffect(() => {
    if (!wanted) return;
    let live = true;
    fetch("/badges", { credentials: "same-origin", headers: { accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: Record<string, unknown> | null) => {
        if (!live || !body) return;
        const counts: Record<string, number> = {};
        for (const [id, count] of Object.entries(body)) if (typeof count === "number") counts[id] = count;
        setUnseen(counts);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [wanted]);
  return unseen;
}

function Companion({
  module,
  unseen,
  children,
}: {
  module: ModuleSummary;
  unseen: number;
  children: React.ReactNode;
}) {
  return (
    <a
      className="launcher-companion"
      href={module.view ?? module.api_prefix}
      title={module.name}
      aria-label={unseen > 0 ? `${module.name}, ${unseen} sin ver` : module.name}
    >
      {children}
      {unseen > 0 && <span className="launcher-companion-dot" aria-hidden="true" />}
    </a>
  );
}

const today = () => zonedDates({ weekday: "long", day: "numeric", month: "long" });

export function Launcher({
  modules,
  search,
  iconStyle = "solid",
}: {
  modules: ModuleSummary[];
  search?: React.ReactNode;
  iconStyle?: IconStyle;
}) {
  const [missing, setMissing] = React.useState<Set<string>>(new Set());
  const [plain, setPlain] = React.useState<Set<string>>(new Set());
  const unseen = useUnseen(modules);

  if (modules.length === 0) {
    return (
      <EmptyState icon="modules" title="No hay módulos instalados">
        Los widgets que ves ahora son del propio sistema. Cuando instales un módulo —finanzas, salud,
        objetivos— aparecerá aquí y traerá los suyos.
      </EmptyState>
    );
  }

  const icon = (module: ModuleSummary) =>
    module.view && !missing.has(module.id) ? (
      <img
        className="launcher-icon launcher-icon-image"
        src={plain.has(module.id) ? appIconOf(module) : styledIcon(appIconOf(module)!, iconStyle)}
        alt=""
        onError={() =>
          plain.has(module.id)
            ? setMissing((previous) => new Set(previous).add(module.id))
            : setPlain((previous) => new Set(previous).add(module.id))
        }
      />
    ) : (
      <span className="launcher-icon" data-hue={1} aria-hidden="true">
        {module.name.slice(0, 1)}
      </span>
    );

  const { pinned, companions, families, fillers } = groupModules(modules);
  const { order, placed } = placeBlocks(
    families.map((family) => family.modules),
    fillers,
  );

  return (
    <div className="launcher-home">
      <div className="launcher-top">
        {pinned.map((module) => (
          <a key={module.id} className="launcher-band" href={module.view ?? module.api_prefix}>
            {icon(module)}
            <span className="launcher-band-text">
              <span className="launcher-band-name">{module.name}</span>
              <span className="launcher-band-date" suppressHydrationWarning>
                {today().format(new Date())}
              </span>
            </span>
          </a>
        ))}
        {search}
        {companions.map((module) => (
          <Companion key={module.id} module={module} unseen={unseen[module.id] ?? 0}>
            {icon(module)}
          </Companion>
        ))}
      </div>
      <ul className="launcher-all">
        {order.map((module) => (
          <li
            key={module.id}
            style={
              {
                "--launcher-column": placed.get(module.id)?.phone[0],
                "--launcher-row": placed.get(module.id)?.phone[1],
                "--launcher-column-wide": placed.get(module.id)?.desktop[0],
                "--launcher-row-wide": placed.get(module.id)?.desktop[1],
              } as React.CSSProperties
            }
          >
            <a className="launcher-app" href={module.view ?? module.api_prefix}>
              {icon(module)}
              <span className="launcher-name">{module.name}</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
