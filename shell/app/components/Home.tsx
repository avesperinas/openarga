"use client";

import { AreaPanel, AreaPanelSkeleton, Icon, IconButton, PanelBlockView, type IconName } from "@openarga/ui";
import * as React from "react";

import type { WidgetSize } from "../lib/kernel";
import { AREAS, type AreaKey, type Contributor, ask, compose, splitActing } from "../lib/panels";
import { request } from "../lib/session";

type Focus = { area: AreaKey; tab?: string; board?: boolean };

const STALE_MS = 5 * 60_000;

const CHECK_MS = 15_000;

type Home = {
  known: Partial<Record<AreaKey, Contributor[]>>;
  learn: (area: AreaKey, contributors: Contributor[]) => void;
  act: (area: AreaKey, acting: string, verb: "complete" | "reopen" | "add", id: string) => Promise<void>;
  jump: React.MutableRefObject<((area: AreaKey) => boolean) | null>;
  setFocus: (focus: Focus | null) => void;
};

const Context = React.createContext<Home | null>(null);

export const useHome = () => React.useContext(Context);

export async function fetchAreas(query: string): Promise<Partial<Record<AreaKey, Contributor[]>>> {
  const response = await fetch(`/panels?${query}`, { cache: "no-store" });
  if (!response.ok) return {};
  return ((await response.json()) as { areas: Partial<Record<AreaKey, Contributor[]>> }).areas;
}

export const areaInfo = (key: AreaKey) => {
  const meta = AREAS.find((area) => area.key === key)!;
  return { key, label: meta.label, hue: meta.hue, icon: <Icon name={meta.icon as IconName} />, apps: "" };
};

export function HomeProvider({ children }: { children: React.ReactNode }) {
  const [known, setKnown] = React.useState<Partial<Record<AreaKey, Contributor[]>>>({});
  const [focus, setFocus] = React.useState<Focus | null>(null);
  const jump = React.useRef<((area: AreaKey) => boolean) | null>(null);

  const fetched = React.useRef<Partial<Record<AreaKey, number>>>({});
  const learn = React.useCallback((area: AreaKey, contributors: Contributor[]) => {
    fetched.current[area] = Date.now();
    setKnown((before) => (before[area] === contributors ? before : { ...before, [area]: contributors }));
  }, []);

  React.useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      for (const [area, at] of Object.entries(fetched.current)) {
        if (now - (at ?? 0) < STALE_MS) continue;
        fetched.current[area as AreaKey] = now;
        void fetchAreas(`area=${area}`).then((found) => {
          const fresh = found[area as AreaKey];
          if (fresh) learn(area as AreaKey, fresh);
        });
      }
    };
    const timer = window.setInterval(refresh, CHECK_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [learn]);

  const act = React.useCallback(
    async (area: AreaKey, acting: string, verb: "complete" | "reopen" | "add", id: string) => {
      const { source, widget } = splitActing(acting);
      const response = await request(`/api/${source}/widgets/${widget}/act`, {
        method: "POST",
        headers: { accept: "application/json", "content-type": "application/json" },
        body: JSON.stringify({ verb, id }),
      });
      if (!response.ok) return;
      const fresh = (await fetchAreas(`area=${area}`))[area];
      if (fresh) learn(area, fresh);
    },
    [learn],
  );

  const value = React.useMemo(() => ({ known, learn, act, jump, setFocus }), [known, learn, act]);
  return (
    <Context.Provider value={value}>
      {children}
      {focus && <FocusSheet focus={focus} onFocus={setFocus} />}
    </Context.Provider>
  );
}

function composed(area: AreaKey, contributors: Contributor[]) {
  return compose(contributors, { order: [area], hidden: [] }).find((one) => one.key === area) ?? null;
}

function FocusSheet({ focus, onFocus }: { focus: Focus; onFocus: (focus: Focus | null) => void }) {
  const home = useHome()!;
  const contributors = home.known[focus.area];
  const area = contributors ? composed(focus.area, contributors) : null;

  React.useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && onFocus(null);
    document.addEventListener("keydown", close);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", close);
      document.body.style.overflow = overflow;
    };
  }, [onFocus]);

  const info = { ...areaInfo(focus.area), apps: area?.apps ?? "" };
  return (
    <div className="home-focus" role="dialog" aria-modal="true" aria-label={info.label} onClick={(event) => event.target === event.currentTarget && onFocus(null)}>
      <div className="home-focus-sheet">
        {area ? (
          <AreaPanel
            area={info}
            headline={area.headline}
            tabs={area.tabs}
            focus
            board={focus.board}
            tab={focus.tab}
            onTab={(id) => onFocus({ ...focus, tab: id })}
            onExpand={() => onFocus(null)}
            onAct={(acting, verb, id) => home.act(focus.area, acting, verb, id)}
          />
        ) : (
          <AreaPanelSkeleton area={info} />
        )}
      </div>
    </div>
  );
}

export function PanelPage({
  area,
  initial,
  board,
  editing = false,
  first = false,
  last = false,
  onMove,
  onRemove,
}: {
  area: AreaKey;
  initial?: Promise<Contributor[]>;
  board: boolean;
  editing?: boolean;
  first?: boolean;
  last?: boolean;
  onMove?: (step: -1 | 1) => void;
  onRemove?: () => void;
}) {
  const label = areaInfo(area).label;
  return (
    <div className="panel-page">
      {editing && (
        <div className="panel-page-tools">
          <IconButton icon="chevron-left" label={`Mover ${label} a la izquierda`} size="small" variant="plain" disabled={first} onClick={() => onMove?.(-1)} />
          <IconButton icon="trash" label={`Quitar el panel de ${label}`} size="small" variant="plain" onClick={onRemove} />
          <IconButton icon="chevron-right" label={`Mover ${label} a la derecha`} size="small" variant="plain" disabled={last} onClick={() => onMove?.(1)} />
        </div>
      )}
      <React.Suspense fallback={<AreaPanelSkeleton area={areaInfo(area)} board={board} />}>
        <LivePanel area={area} initial={initial} board={board} />
      </React.Suspense>
    </div>
  );
}

function LivePanel({ area, initial, board }: { area: AreaKey; initial?: Promise<Contributor[]>; board: boolean }) {
  const home = useHome();
  const arrived = initial ? React.use(initial) : undefined;
  const learn = home?.learn;
  const [own, setOwn] = React.useState<Contributor[] | undefined>(arrived);
  const [tab, setTab] = React.useState<string | undefined>(undefined);

  React.useEffect(() => {
    if (arrived) learn?.(area, arrived);
  }, [area, arrived, learn]);

  React.useEffect(() => {
    if (arrived) return;
    let alive = true;
    void fetchAreas(`area=${area}`).then((found) => {
      const list = found[area] ?? [];
      if (!alive) return;
      setOwn(list);
      learn?.(area, list);
    });
    return () => {
      alive = false;
    };
  }, [area, arrived, learn]);

  const contributors = home?.known[area] ?? own;
  if (!contributors) return <AreaPanelSkeleton area={areaInfo(area)} board={board} />;
  const found = composed(area, contributors);
  return (
    <AreaPanel
      area={{ ...areaInfo(area), apps: found?.apps ?? "" }}
      headline={found?.headline ?? null}
      tabs={found?.tabs ?? []}
      board={board}
      tab={tab}
      onTab={setTab}
      onExpand={board ? undefined : () => home?.setFocus({ area, tab })}
      onAct={home ? (acting, verb, id) => home.act(area, acting, verb, id) : undefined}
    />
  );
}

const BLOCKS_BY_SIZE: Partial<Record<WidgetSize, number>> = { "2x2": 1, "4x2": 1, "4x4": 3 };

const GRAPHIC = ["rings", "trend", "bars", "split", "treemap", "feature", "figure", "tiles", "month", "timeline", "tasks", "alert", "list"];

export function PanelWidget({
  area,
  tab,
  size,
  initial,
  board,
}: {
  area: AreaKey;
  tab?: string | null;
  size: WidgetSize;
  initial?: Promise<Contributor[]>;
  board: boolean;
}) {
  return (
    <div className="panel-widget" data-size={size} data-single={tab ? "" : undefined}>
      <React.Suspense fallback={<AreaPanelSkeleton area={areaInfo(area)} />}>
        <LiveWidget area={area} tab={tab ?? null} size={size} initial={initial} board={board} />
      </React.Suspense>
    </div>
  );
}

function useArea(area: AreaKey, initial?: Promise<Contributor[]>) {
  const home = useHome();
  const arrived = initial ? React.use(initial) : undefined;
  const learn = home?.learn;
  const [own, setOwn] = React.useState<Contributor[] | undefined>(arrived);
  React.useEffect(() => {
    if (arrived) learn?.(area, arrived);
  }, [area, arrived, learn]);
  React.useEffect(() => {
    if (arrived || home?.known[area]) return;
    let alive = true;
    void fetchAreas(`area=${area}`).then((found) => {
      const list = found[area] ?? [];
      if (!alive) return;
      setOwn(list);
      learn?.(area, list);
    });
    return () => {
      alive = false;
    };
  }, [area, arrived, learn]);
  return { home, contributors: home?.known[area] ?? own };
}

function LiveWidget({ area, tab, size, initial, board }: { area: AreaKey; tab: string | null; size: WidgetSize; initial?: Promise<Contributor[]>; board: boolean }) {
  const { home, contributors } = useArea(area, initial);
  const [shown, setShown] = React.useState<string | undefined>(undefined);
  if (!contributors) return <AreaPanelSkeleton area={areaInfo(area)} />;
  const found = composed(area, contributors);
  const act = home ? (acting: string, verb: "complete" | "reopen" | "add", id: string) => home.act(area, acting, verb, id) : undefined;
  if (!tab) {
    return (
      <AreaPanel
        area={{ ...areaInfo(area), apps: found?.apps ?? "" }}
        headline={found?.headline ?? null}
        tabs={found?.tabs ?? []}
        tab={shown}
        onTab={setShown}
        onExpand={() => home?.setFocus({ area, tab: shown, board })}
        onAct={act}
      />
    );
  }
  const one = found?.tabs.find((candidate) => candidate.id === tab);
  const source = tab.split(".")[0];
  const app = contributors.find((candidate) => candidate.source === source)?.name ?? "";
  const limit = BLOCKS_BY_SIZE[size] ?? 2;
  const visible = (one?.blocks ?? []).filter((block) => !block.detail);
  const blocks =
    visible.length > limit && !visible.some((block) => block.type === "tasks")
      ? [...visible].sort((a, b) => GRAPHIC.indexOf(a.type) - GRAPHIC.indexOf(b.type)).slice(0, limit)
      : visible.slice(0, limit);
  return (
    <AreaPanel
      area={{ ...areaInfo(area), label: one?.label ?? areaInfo(area).label, apps: app }}
      tabs={one ? [{ ...one, blocks, actions: size === "4x4" ? one.actions : [] }] : []}
      onExpand={size === "2x2" ? undefined : () => home?.setFocus({ area, tab, board })}
      onAct={act}
    />
  );
}

export function Ask() {
  const home = useHome();
  const [query, setQuery] = React.useState("");
  const asked = React.useRef(false);

  const everything = () => {
    if (asked.current || !home) return;
    asked.current = true;
    void fetchAreas("all=1").then((found) => {
      for (const [area, contributors] of Object.entries(found)) home.learn(area as AreaKey, contributors ?? []);
    });
  };

  const areas = React.useMemo(
    () => compose(Object.values(home?.known ?? {}).flat(), { hidden: [] }),
    [home?.known],
  );
  const answers = React.useMemo(() => ask(areas, query), [areas, query]);
  const open = (area: AreaKey, tab: string) => {
    setQuery("");
    if (!home?.jump.current?.(area)) home?.setFocus({ area, tab });
  };

  return (
    <div className="home-ask">
      <label className="home-ask-field">
        <Icon name="search" />
        <input
          type="search"
          value={query}
          onFocus={everything}
          onChange={(event) => {
            everything();
            setQuery(event.target.value);
          }}
          placeholder="Pregunta: vacaciones, renta, fin de mes…"
          aria-label="Pregunta a tus apps"
        />
      </label>
      {query.trim().length >= 2 && (
        <div className="home-answers" role="region" aria-live="polite" aria-label="Respuestas">
          {answers.length === 0 ? (
            <p className="home-answers-none">{asked.current && Object.keys(home?.known ?? {}).length < AREAS.length ? "Buscando…" : "Ninguna app contesta a eso todavía."}</p>
          ) : (
            answers.map((answer) => {
              const area = areas.find((one) => one.key === answer.area)!;
              return (
                <article key={`${answer.tab}-${answer.text}`} className="home-answer" data-hue={area.hue}>
                  <header>
                    <span>{area.label}</span>
                    <b>{answer.text}</b>
                  </header>
                  {answer.block && <PanelBlockView block={answer.block} onAct={(acting, verb, id) => home?.act(answer.area, acting, verb, id) ?? Promise.resolve()} />}
                  <button type="button" onClick={() => open(answer.area, answer.tab)}>
                    Ver en {area.label}
                  </button>
                </article>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
