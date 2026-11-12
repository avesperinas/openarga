"use client";

import { Button, Icon, IconButton, entrance, type IconName, type PageTab } from "@openarga/ui";
import * as React from "react";

import { BATCH, envelopeKey, missing, parseEnvelopeKey, stale, widgetUrl } from "../lib/envelope";
import type { CatalogueEntry, DeskItem, DesktopLayout, Device, Envelope, LayoutItem } from "../lib/kernel";
import {
  BREAKPOINTS,
  COLUMNS,
  GAP,
  add,
  arrange,
  arrangeAll,
  autoArrange,
  createPage,
  isArrangedByHand,
  move,
  resize,
  spanOf,
} from "../lib/layout";
import {
  AREAS,
  type AreaKey,
  type Contributor,
  PANEL_SOURCE,
  PANELS_PER_DESKTOP_PAGE,
  groupPanelPages,
  panelAreaOf,
  panelEntries,
  shownAreas,
  withPanelPages,
} from "../lib/panels";
import { groupPages } from "../lib/paging";
import { request } from "../lib/session";
import { AddSheet } from "./AddSheet";
import { useDesktop } from "./Desktop";
import { PanelWidget, useHome } from "./Home";
import {
  UndoToast,
  movePage,
  remove,
  removePage,
  useBreakpoint,
  useDevice,
  useEditableDesk,
  useGrid,
} from "./Editable";
import { Pages } from "./Pages";
import { DeletePageDialog } from "./Screens";
import { WidgetCard } from "./WidgetCard";

export function Dashboard({
  desks,
  device: guess,
  ...rest
}: {
  desks: Record<Device, DesktopLayout>;
  device: Device;
  catalogue: CatalogueEntry[];
  data?: Record<string, Envelope | null>;
  pending?: Record<string, Promise<Envelope | null>>;
  icons?: Record<string, string>;
  panels?: Partial<Record<AreaKey, Promise<Contributor[]>>>;
}) {
  const device = useDevice(guess);
  const mobile = useEditableDesk(desks.mobile, "mobile");
  const desktop = useEditableDesk(desks.desktop, "desktop");
  const memory = useMemory(rest.pending);
  return (
    <DeviceDashboard
      key={device}
      device={device}
      board={device === "desktop"}
      editable={device === "mobile" ? mobile : desktop}
      memory={memory}
      {...rest}
    />
  );
}

function useMemory(pending: Record<string, Promise<Envelope | null>> = {}) {
  const [fetched, setFetched] = React.useState<Record<string, Envelope | null>>({});
  const arrived = React.useRef<Record<string, number>>({});
  const asked = React.useRef(new Set<string>());
  const generation = React.useRef<Record<string, number>>({});
  React.useEffect(() => {
    for (const [key, promise] of Object.entries(pending)) {
      void promise.then(() => {
        arrived.current[key] ??= Date.now();
      });
    }
  }, [pending]);
  return { fetched, setFetched, arrived, asked, generation };
}

type Memory = ReturnType<typeof useMemory>;

function DeviceDashboard({
  editable,
  catalogue,
  data = {},
  pending = {},
  icons = {},
  panels,
  board,
  device,
  memory,
}: {
  device: Device;
  panels?: Partial<Record<AreaKey, Promise<Contributor[]>>>;
  board: boolean;
  editable: ReturnType<typeof useEditableDesk>;
  memory: Memory;
  catalogue: CatalogueEntry[];
  data?: Record<string, Envelope | null>;
  pending?: Record<string, Promise<Envelope | null>>;
  icons?: Record<string, string>;
}) {
  const desktop = useDesktop();
  const editing = desktop?.editing ?? false;
  const onEditing = React.useCallback(
    (next: boolean) => desktop?.setEditing(next),
    [desktop],
  );

  const { desk, apply, undo, setUndo, notice, setNotice } = editable;
  const { pages } = desk;
  const breakpoint = useBreakpoint();
  const columns = COLUMNS[breakpoint];
  const onMove = React.useCallback(
    (id: string, target: { page: number; x: number; y: number }) =>
      apply((current) => {
        const base =
          target.page < current.pages.length
            ? current
            : createPage(current, crypto.randomUUID());
        return move(base, id, breakpoint, { ...target, page: Math.min(target.page, base.pages.length - 1) });
      }),
    [apply, breakpoint],
  );
  const onResize = React.useCallback(
    (id: string, size: LayoutItem["size"]) => apply((current) => resize(current, id, size)),
    [apply],
  );
  const arranged = React.useMemo(() => arrangeAll(desk, breakpoint), [desk, breakpoint]);
  const grid = useGrid(arranged, onMove, onResize, columns, GAP[breakpoint]);
  const [adding, setAdding] = React.useState(false);
  const [deleting, setDeleting] = React.useState<number | null>(null);
  const [current, setCurrent] = React.useState(0);
  const [jump, setJump] = React.useState<{ index: number; at: number } | null>(null);
  const home = useHome();
  React.useEffect(() => {
    if (!home) return;
    home.jump.current = (area) => {
      const index = pages.findIndex((page) => page.items.some((item) => panelAreaOf(item) === area && !item.option));
      if (index < 0) return false;
      setJump({ index, at: Date.now() });
      return true;
    };
    return () => {
      home.jump.current = null;
    };
  });

  const migrated = React.useRef(false);
  React.useEffect(() => {
    if (!panels || !desktop || migrated.current) return;
    migrated.current = true;
    const before = desktop.preferences.home_panels;
    const perPage = device === "desktop" ? PANELS_PER_DESKTOP_PAGE : 1;
    if (!before?.placed?.includes(device)) {
      apply((now) => withPanelPages(now, shownAreas(before), () => crypto.randomUUID(), perPage));
      desktop.change({ home_panels: { ...before, placed: [...(before?.placed ?? []), device] } });
      return;
    }
    if (device === "desktop" && groupPanelPages(desk) !== desk) apply((now) => groupPanelPages(now));
  });

  const byId = new Map(catalogue.map((entry) => [`${entry.source}/${entry.id}`, entry]));
  const panelCatalogue = React.useMemo(() => (panels ? panelEntries() : []), [panels]);
  const entryOf = (item: { source: string; widget: string }) =>
    byId.get(`${item.source}/${item.widget}`) ?? panelCatalogue.find((entry) => entry.source === item.source && entry.id === item.widget);
  const everything = pages.flatMap((page) => page.items);
  const all = everything.filter((item) => item.source !== PANEL_SOURCE);
  const placed = new Set(everything.filter((item) => !item.option).map((item) => `${item.source}/${item.widget}`));
  const dragged = everything.find((item) => item.instance_id === grid.dragging);

  const quitar = (instanceId: string, label: string) => {
    setUndo({ desk, label });
    apply((current) => remove(current, instanceId));
  };

  const { fetched, setFetched, arrived, generation } = memory;
  const envelopes = { ...data, ...fetched };
  const known = { ...pending, ...envelopes };

  const touch = React.useCallback(
    (key: string) => {
      const now = (generation.current[key] ?? 0) + 1;
      generation.current[key] = now;
      return () => generation.current[key] === now;
    },
    [generation],
  );

  const refetch = React.useCallback(
    (entry: CatalogueEntry, option?: string | null) => {
      const key = envelopeKey(entry.source, entry.id, option);
      const current = touch(key);
      request(widgetUrl(entry.endpoint, option), { headers: { accept: "application/json" } })
        .then((response) => (response.ok ? (response.json() as Promise<Envelope>) : null))
        .catch(() => null)
        .then((envelope) => {
          if (!current()) return;
          arrived.current[key] = Date.now();
          setFetched((previous) => ({ ...previous, [key]: envelope }));
        });
    },
    [arrived, setFetched, touch],
  );

  const latest = React.useRef<{
    data: Record<string, Envelope | null>;
    keys: string[];
    refreshOf: (key: string) => number | undefined;
  }>({ data, keys: [], refreshOf: () => undefined });
  latest.current = {
    data,
    keys: all.map((item) => envelopeKey(item.source, item.widget, item.option)),
    refreshOf: (key) => byId.get(parseEnvelopeKey(key).widget)?.refresh,
  };
  React.useEffect(() => {
    const loaded = Date.now();
    for (const key of Object.keys(latest.current.data)) arrived.current[key] ??= loaded;
    let busy = false;
    const repaint = () => {
      if (busy || document.visibilityState !== "visible") return;
      const { keys, refreshOf } = latest.current;
      const due = stale(keys, refreshOf, arrived.current, Date.now()).slice(0, BATCH);
      if (!due.length) return;
      busy = true;
      const asked = Date.now();
      const sent: Record<string, number | undefined> = {};
      for (const key of due) {
        arrived.current[key] = asked;
        sent[key] = generation.current[key];
      }
      request(`/envelopes?${due.map((key) => `w=${encodeURIComponent(key)}`).join("&")}`, {
        headers: { accept: "application/json" },
      })
        .then((response) =>
          response.ok ? (response.json() as Promise<Record<string, Envelope | null>>) : {},
        )
        .catch((): Record<string, Envelope | null> => ({}))
        .then((answers: Record<string, Envelope | null>) => {
          const fresh: Record<string, Envelope> = {};
          for (const [key, envelope] of Object.entries(answers)) {
            if (envelope && key in sent && generation.current[key] === sent[key]) fresh[key] = envelope;
          }
          if (Object.keys(fresh).length) setFetched((previous) => ({ ...previous, ...fresh }));
        })
        .finally(() => {
          busy = false;
        });
    };
    const timer = window.setInterval(repaint, 15_000);
    document.addEventListener("visibilitychange", repaint);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", repaint);
    };
  }, [arrived, generation, setFetched]);

  const { asked } = memory;
  React.useEffect(() => {
    for (const item of missing(all, known)) {
      const key = envelopeKey(item.source, item.widget, item.option);
      const entry = byId.get(`${item.source}/${item.widget}`);
      if (!entry || asked.current.has(key)) continue;
      asked.current.add(key);
      refetch(entry, item.option);
    }
  });

  const act = React.useCallback(
    async (entry: CatalogueEntry, option: string | null | undefined, verb: string, id: string): Promise<boolean> => {
      const key = envelopeKey(entry.source, entry.id, option);
      const current = touch(key);
      try {
        const response = await request(widgetUrl(`${entry.endpoint}/act`, option), {
          method: "POST",
          headers: { accept: "application/json", "content-type": "application/json" },
          body: JSON.stringify({ verb, id }),
        });
        if (!response.ok) return false;
        const envelope = (await response.json()) as Envelope;
        if (current()) {
          arrived.current[key] = Date.now();
          setFetched((previous) => ({ ...previous, [key]: envelope }));
        }
        return true;
      } catch {
        return false;
      }
    },
    [arrived, setFetched, touch],
  );

  const anadir = (entry: CatalogueEntry, option?: string) => {
    setAdding(false);
    const instance = crypto.randomUUID();
    const page = current;
    const fresh = crypto.randomUUID();
    apply((now) => {
      const base = page < now.pages.length ? now : createPage(now, fresh);
      return add(base, Math.min(page, base.pages.length - 1), {
        instance_id: instance,
        source: entry.source,
        widget: entry.id,
        size: entry.sizes[0] ?? "2x2",
        ...(option ? { option } : {}),
      });
    });

    if (entry.source !== PANEL_SOURCE && !(envelopeKey(entry.source, entry.id, option) in known)) refetch(entry, option);

    requestAnimationFrame(() =>
      document
        .querySelector(`.dashboard [data-instance="${instance}"]`)
        ?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" }),
    );
  };

  const borrar = (index: number) => {
    if (pages[index]?.items.length) return setDeleting(index);
    apply((now) => removePage(now, index, false));
  };

  const spansOf = (all: typeof pages) =>
    groupPages(
      all.map(
        (page) =>
          Math.max(
            0,
            ...arrange(page, COLUMNS.desktop, desk.placements.desktop?.[page.id]).map(
              (item) => item.x + spanOf(item.size)[0],
            ),
          ) || COLUMNS.desktop,
      ),
    );

  const placedIn = (page: (typeof pages)[number]) => {
    const where = Object.fromEntries(
      BREAKPOINTS.map((name) => [
        name,
        new Map(
          arrange(page, COLUMNS[name], desk.placements[name]?.[page.id]).map((item) => [
            item.instance_id,
            item,
          ]),
        ),
      ]),
    ) as Record<(typeof BREAKPOINTS)[number], Map<string, LayoutItem>>;
    return page.items.map(
      (item) =>
        [
          item,
          {
            mobile: where.mobile.get(item.instance_id)!,
            tablet: where.tablet.get(item.instance_id)!,
            desktop: where.desktop.get(item.instance_id)!,
          },
        ] as const,
    );
  };

  let order = 0;

  return (
    <div className="dashboard" data-editing={editing || undefined}>
      <Pages onCurrent={setCurrent} tabs={panels ? tabsOf(pages, editing) : undefined} jump={jump} spans={editing ? undefined : spansOf(pages)}>
        {[
          ...pages.map((page, pageIndex) => (
            <React.Fragment key={page.id}>
              {editing && (
                <div className="page-tools">
                  <IconButton
                    icon="chevron-left"
                    label="Mover la pantalla a la izquierda"
                    size="small"
                    disabled={pageIndex === 0}
                    onClick={() => apply((now) => movePage(now, pageIndex, pageIndex - 1))}
                  />
                  <IconButton
                    icon="chevron-right"
                    label="Mover la pantalla a la derecha"
                    size="small"
                    disabled={pageIndex === pages.length - 1}
                    onClick={() => apply((now) => movePage(now, pageIndex, pageIndex + 1))}
                  />
                  {isArrangedByHand(desk, breakpoint, page.id) && (
                    <IconButton
                      icon="modules"
                      label="Colocar solos los widgets de esta pantalla"
                      size="small"
                      onClick={() => apply((now) => autoArrange(now, breakpoint, page.id))}
                    />
                  )}
                  <IconButton
                    icon="trash"
                    label={`Borrar la pantalla ${pageIndex + 1}`}
                    size="small"
                    variant="destructive"
                    disabled={pages.length < 2}
                    onClick={() => borrar(pageIndex)}
                  />
                </div>
              )}

              <div className="grid" data-page={pageIndex}>
                {editing && grid.target?.page === pageIndex && dragged && (
                  <div
                    className="grid-target"
                    style={
                      {
                        ...cellVars(grid.target, grid.target, grid.target),
                        "--w": spanOf(dragged.size)[0],
                        "--h": spanOf(dragged.size)[1],
                      } as React.CSSProperties
                    }
                  />
                )}

                {placedIn(page).map(([item, where]) => {
                  const entry = entryOf(item);
                  const area = panelAreaOf(item);
                  const title = entry?.title ?? item.widget;
                  const shown =
                    grid.resizing === item.instance_id && grid.pending ? grid.pending : item.size;
                  const [width, height] = spanOf(shown);
                  const index = order++;
                  const link = editing ? undefined : (entry?.link ?? undefined);

                  return (
                    <div
                      key={item.instance_id}
                      className="grid-cell widget-enter"
                      data-instance={item.instance_id}
                      data-dragging={grid.dragging === item.instance_id || undefined}
                      style={
                        {
                          ...entrance(index),
                          ...cellVars(where.mobile, where.tablet, where.desktop),
                          "--w": width,
                          "--h": height,
                        } as React.CSSProperties
                      }
                      onPointerDown={editing ? grid.start(item.instance_id) : undefined}
                    >
                      {editing && (
                        <>
                          <button
                            type="button"
                            className="grid-remove"
                            aria-label={`Quitar ${title}`}
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={() => quitar(item.instance_id, title)}
                          >
                            <Icon name="close" />
                          </button>
                          {(entry?.sizes.length ?? 0) > 1 && (
                            <span
                              className="grid-grip"
                              role="slider"
                              tabIndex={0}
                              aria-label={`Cambiar el tamaño de ${title}`}
                              aria-valuetext={item.size}
                              onPointerDown={grid.startResize(
                                item.instance_id,
                                entry?.sizes ?? [],
                              )}
                            />
                          )}
                        </>
                      )}
                      {(() => {
                        if (area) {
                          return (
                            <PanelWidget area={area} tab={item.option} size={item.size} initial={panels?.[area]} board={board} />
                          );
                        }
                        const key = envelopeKey(item.source, item.widget, item.option);
                        const card = (envelope: Envelope | null | undefined) => (
                          <WidgetCard
                            item={item}
                            entry={entry}
                            appIcon={icons[item.source]}
                            link={link}
                            onRetry={entry ? () => refetch(entry, item.option) : undefined}
                            onAct={
                              entry && !editing
                                ? (verb: string, id: string) => act(entry, item.option, verb, id)
                                : undefined
                            }
                            envelope={envelope}
                          />
                        );
                        if (key in envelopes || !(key in pending)) {
                          return card(key in envelopes ? (envelopes[key] ?? null) : undefined);
                        }
                        return (
                          <React.Suspense fallback={card(undefined)}>
                            <Arriving promise={pending[key]!}>{card}</Arriving>
                          </React.Suspense>
                        );
                      })()}
                      {link && (
                        <a
                          className="grid-open"
                          href={link}
                          aria-label={`Abrir ${title}`}
                          draggable={false}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </React.Fragment>
          )),
          ...(editing
            ? [
                <div
                  key="fantasma"
                  className="grid grid-ghost"
                  data-page={pages.length}
                >
                  <p className="grid-ghost-hint">
                    <Icon name="plus" />
                    Suelta un widget aquí para crear otra pantalla
                  </p>
                </div>,
              ]
            : []),
        ]}
      </Pages>

      {editing && (
        <div className="glass editbar" role="toolbar" aria-label="Edición">
          <Button variant="plain" icon="plus" onClick={() => setAdding(true)}>
            Añadir
          </Button>
          <Button variant="primary" icon="done" onClick={() => onEditing(false)}>
            Hecho
          </Button>
        </div>
      )}

      {adding && (
        <AddSheet
          catalogue={[...panelCatalogue, ...catalogue]}
          placed={placed}
          onPick={anadir}
          onClose={() => setAdding(false)}
        />
      )}

      {deleting !== null && (
        <DeletePageDialog
          index={deleting}
          count={pages[deleting]?.items.length ?? 0}
          onResolve={(keep) => {
            if (keep !== null) apply((now) => removePage(now, deleting, keep));
            setDeleting(null);
          }}
        />
      )}

      <UndoToast
        undo={undo}
        onUndo={() => {
          if (undo) apply(() => undo.desk);
          setUndo(null);
        }}
        onDismiss={() => setUndo(null)}
      />
      <Notice text={notice} onDismiss={() => setNotice(null)} />
    </div>
  );
}

function Arriving({
  promise,
  children,
}: {
  promise: Promise<Envelope | null>;
  children: (envelope: Envelope | null) => React.ReactNode;
}) {
  return children(React.use(promise));
}

type At = { x: number; y: number };

const cellVars = (mobile: At, tablet: At, desktop: At) => ({
  "--xm": mobile.x + 1,
  "--ym": mobile.y + 1,
  "--xt": tablet.x + 1,
  "--yt": tablet.y + 1,
  "--xd": desktop.x + 1,
  "--yd": desktop.y + 1,
});

function Notice({ text, onDismiss }: { text: string | null; onDismiss: () => void }) {
  React.useEffect(() => {
    if (!text) return;
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [text, onDismiss]);

  if (!text) return null;
  return (
    <div className="glass toast" role="status">
      <span>{text}</span>
    </div>
  );
}

function tabsOf(pages: { id: string; items: DeskItem[] }[], editing: boolean): PageTab[] {
  let plain = 0;
  const tabs = pages.map((page): PageTab => {
    const key = page.items.map((item) => (item.option ? null : panelAreaOf(item))).find((one) => one !== null);
    const area = key ? AREAS.find((one) => one.key === key) : undefined;
    if (area) return { key: page.id, label: area.label, hue: area.hue, icon: <Icon name={area.icon as IconName} /> };
    plain += 1;
    return { key: page.id, label: "Widgets" };
  });
  if (plain > 1) {
    let n = 0;
    for (const tab of tabs) if (tab.label === "Widgets") tab.label = `Widgets ${++n}`;
  }
  return [...tabs, ...(editing ? [{ key: "nueva", label: "Nueva" }] : [])];
}
