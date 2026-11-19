"use client";

import { EmptyState, type IconStyle, regional, styledIcon } from "@openarga/ui";
import * as React from "react";

import { appIconOf } from "../lib/app-icons";
import type { ModuleSummary } from "../lib/kernel";
import { say } from "../words";

export const FAMILY_ORDER = ["calendar", "health", "goals", "finance", "growth", "wellbeing", "companion"] as const;

const LAST = "system";

// Within a family, what people open every day comes first.
const DAILY = [
  "planner",
  "macros",
  "training",
  "vitals",
  "recipes",
  "goals",
  "shopping",
  "money",
  "notebook",
  "study",
  "outings",
  "library",
  "travel",
  "insights",
  "hub",
];

const rankOf = (module: ModuleSummary) => {
  const family = module.family ?? "";
  if (family === LAST) return FAMILY_ORDER.length + 1;
  const known = (FAMILY_ORDER as readonly string[]).indexOf(family);
  return known === -1 ? FAMILY_ORDER.length : known;
};

export function orderModules(modules: ModuleSummary[]): ModuleSummary[] {
  const daily = (module: ModuleSummary) => {
    const at = DAILY.indexOf(module.id);
    return at === -1 ? DAILY.length : at;
  };
  return [...modules].sort(
    (a, b) =>
      rankOf(a) - rankOf(b) ||
      daily(a) - daily(b) ||
      a.name.localeCompare(b.name, regional().locale),
  );
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
      <EmptyState icon="modules" title={say("launcher.empty")}>
        {say("launcher.empty.hint")}
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

  return (
    <div className="launcher-home">
      {search && <div className="launcher-top">{search}</div>}
      <ul className="launcher-all">
        {orderModules(modules).map((module) => {
          const count = unseen[module.id] ?? 0;
          return (
            <li key={module.id} data-family={module.family}>
              <a
                className="launcher-app"
                href={module.view ?? module.api_prefix}
                aria-label={count > 0 ? say("launcher.unseen", { name: module.name, n: count }) : undefined}
              >
                <span className="launcher-tile">
                  {icon(module)}
                  {count > 0 && <span className="launcher-dot" aria-hidden="true" />}
                </span>
                <span className="launcher-name">{module.name}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
