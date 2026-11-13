import { withTransition } from "@openarga/app";
import {
  AppHome,
  AppSettingsSheet,
  AppShell,
  Badge,
  Button,
  CreateButton,
  dayKey,
  dayStart,
  ErrorState,
  HOUR_HEIGHT,
  Icon,
  IconButton,
  MiniMonth,
  MonthGrid,
  Notice,
  OfflineNotice,
  SegmentedControl,
  Sheet,
  Skeleton,
  TimeGrid,
  type TimeRange,
  useNow,
  useToast,
} from "@openarga/ui";
import * as React from "react";

import { Agenda } from "./Agenda";
import {
  type Layer,
  type Occurrence,
  type Scope,
  Unauthorised,
  VIEWER_TZ,
  createEvent,
  createLayer,
  moveAppEvent,
  readEvent,
  signIn,
  updateEvent,
  updateLayer,
} from "./api";
import { counts, duplicatesOf, isBackground, toGridEvent, useCalendarData, usePreference, useWidth } from "./data";
import { LayerSheet, type ScopeQuestion, ScopeDialog } from "./Dialogs";
import { EventPanel, type Opened } from "./EventPanel";
import { blankForm } from "./form";
import { type Command, Palette } from "./Palette";
import { APP, Sidebar } from "./Sidebar";
import { SubscriptionsSheet } from "./Subscriptions";
import {
  type Place,
  type View,
  VIEWS,
  fetchWindow,
  monthOf,
  parsePlace,
  pathOf,
  scroll,
  step,
  switchView,
  titleOf,
  visibleDays,
} from "./views";
import { t } from "./lang";

const MOBILE = 720;

const isTyping = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export function App() {
  const width = useWidth();
  const mobile = width < MOBILE;
  const nowMs = useNow(60_000);
  const now = React.useMemo(() => new Date(nowMs), [nowMs]);
  const today = dayKey(now);

  const [place, setPlace] = React.useState<Place>(() => parsePlace(window.location.pathname, window.innerWidth, dayKey(new Date())));
  const [hourHeight, setHourHeight] = usePreference<number>("planner:hour-height", HOUR_HEIGHT.default);
  const [sidebarPref, setSidebarPref] = usePreference<boolean>("planner:sidebar", true);
  const [lastLayer, setLastLayer] = usePreference<string | null>("planner:last-layer", null);
  const sidebarOpen = !mobile && sidebarPref;

  const [opened, setOpened] = React.useState<Opened | null>(null);
  const [pending, setPending] = React.useState<TimeRange | null>(null);
  const [scopeAsk, setScopeAsk] = React.useState<ScopeQuestion | null>(null);
  const [layerEdit, setLayerEdit] = React.useState<Layer | null | undefined>(undefined);
  const [palette, setPalette] = React.useState(false);
  const [subscribing, setSubscribing] = React.useState(false);
  const [settings, setSettings] = React.useState(false);
  const [awaiting, setAwaiting] = React.useState<string | null>(null);
  const [mobileLayers, setMobileLayers] = React.useState(false);
  const [monthPicker, setMonthPicker] = React.useState(false);
  const toast = useToast();
  const [wantEvent, setWantEvent] = React.useState<string | null>(() => new URLSearchParams(window.location.search).get("event"));

  const view: View = mobile && place.view === "week" ? "three" : place.view;
  const shown: Place = React.useMemo(() => ({ ...place, view }), [place, view]);
  const days = React.useMemo(() => visibleDays(shown), [shown]);
  const window_ = React.useMemo(() => fetchWindow(shown), [shown]);
  const data = useCalendarData(window_.from, window_.to, days.includes(today) ? view : null);

  const placeRef = React.useRef(place);
  placeRef.current = place;

  const go = React.useCallback(
    (next: Place, replace = false) => {
      const update = () => {
        placeRef.current = next;
        setPlace(next);
        const path = pathOf(next, dayKey(new Date()));
        if (path !== window.location.pathname) {
          window.history[replace ? "replaceState" : "pushState"](null, "", path);
        }
      };
      if (next.view !== placeRef.current.view) withTransition(update);
      else update();
    },
    [],
  );
  React.useEffect(() => {
    const back = () =>
      withTransition(() => setPlace(parsePlace(window.location.pathname, window.innerWidth, dayKey(new Date()))));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const { title, week } = titleOf(shown);
  React.useEffect(() => {
    document.title = `${title} · Planner`;
  }, [title]);

  const layers = React.useMemo(() => new Map(data.layers.map((l) => [l.id, l])), [data.layers]);
  const visible = React.useMemo(
    () => data.occurrences.filter((o) => layers.get(o.calendar_id)?.visible !== false && o.status !== "cancelled"),
    [data.occurrences, layers],
  );
  const byId = React.useMemo(() => new Map(visible.map((o) => [o.id, o])), [visible]);
  const twins = React.useMemo(() => duplicatesOf(data.occurrences, data.layers), [data.occurrences, data.layers]);
  const gridEvents = React.useMemo(
    () => visible.map((o) => toGridEvent(o, layers.get(o.calendar_id), layers.get(twins.get(o.id)?.calendar_id ?? "")?.name)),
    [visible, layers, twins],
  );
  const happening = React.useMemo(() => visible.filter((o) => counts(o, layers.get(o.calendar_id))), [visible, layers]);
  const marked = React.useMemo(() => {
    const set = new Set<string>();
    for (const o of happening) set.add(o.all_day ? o.start : dayKey(new Date(o.start)));
    return set;
  }, [happening]);
  const ownLayers = data.layers.filter((l) => l.origin === "own" && !isBackground(l));
  const defaultLayer =
    ownLayers.find((l) => l.id === lastLayer)?.id ??
    ownLayers.find((l) => l.visible)?.id ??
    ownLayers[0]?.id ??
    data.layers.find((l) => l.origin === "own")?.id ??
    "";

  React.useEffect(() => {
    if (!wantEvent) return;
    const found = visible.find((o) => o.event_id === wantEvent);
    if (found) {
      setOpened({ kind: "existing", occurrence: found });
      setWantEvent(null);
      window.history.replaceState(null, "", window.location.pathname);
      return;
    }
    if (data.loading) return;
    let alive = true;
    readEvent(wantEvent)
      .then((event) => {
        if (!alive) return;
        const day = event.all_day ? event.start : dayKey(new Date(event.start));
        if (days.includes(day)) setWantEvent(null);
        else go({ ...place, day }, true);
      })
      .catch(() => alive && setWantEvent(null));
    return () => {
      alive = false;
    };
  }, [wantEvent, visible, data.loading, days, go, place]);

  React.useEffect(() => {
    if (!awaiting) return;
    const layer = data.layers.find((one) => one.id === awaiting);
    if (layer?.subscription?.updated_at || layer?.subscription?.failing) {
      setAwaiting(null);
      if (layer.subscription.failing) toast({ message: `${layer.name}: ${layer.subscription.detail ?? t("sub.failing_short")}`, tone: "error" });
      return;
    }
    const started = Date.now();
    const timer = setInterval(() => {
      if (Date.now() - started > 120_000) {
        setAwaiting(null);
        return;
      }
      void data.reload();
    }, 5_000);
    return () => clearInterval(timer);
  }, [awaiting, data, toast]);

  const fail = React.useCallback((failure: unknown) => {
    if (failure instanceof Unauthorised) return signIn();
    toast({ message: failure instanceof Error ? failure.message : String(failure), tone: "error" });
  }, [toast]);

  const askScope = React.useCallback(
    (question: "edit" | "cancel", allowed: Scope[]) =>
      new Promise<Scope | null>((resolve) =>
        setScopeAsk({
          question,
          allowed,
          resolve: (scope) => {
            setScopeAsk(null);
            resolve(scope);
          },
        }),
      ),
    [],
  );

  const openNew = React.useCallback(
    (range?: TimeRange & { allDay?: boolean }) => {
      let start: Date;
      let end: Date;
      if (range) {
        ({ start, end } = range);
      } else {
        const base = days.includes(today) || view === "month" || view === "agenda" ? today : days[0]!;
        start = base === today ? new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours() + 1) : new Date(dayStart(base).setHours(9));
        end = new Date(start.getTime() + 60 * 60_000);
      }
      setPending(range && !range.allDay ? range : null);
      setOpened({ kind: "new", form: blankForm(start, end, defaultLayer, !!range?.allDay) });
    },
    [days, today, view, now, defaultLayer],
  );

  const onCreate = React.useCallback(
    async (range: TimeRange & { allDay?: boolean }, titleText?: string) => {
      if (!titleText) {
        openNew(range);
        return;
      }
      try {
        await createEvent({
          calendar_id: defaultLayer,
          title: titleText,
          all_day: !!range.allDay,
          start: range.allDay ? dayKey(range.start) : range.start.toISOString(),
          end: range.allDay ? dayKey(range.end) : range.end.toISOString(),
          tz: VIEWER_TZ,
        });
        await data.reload();
      } catch (failure) {
        fail(failure);
      }
    },
    [defaultLayer, data, openNew, fail],
  );

  const onEventChange = React.useCallback(
    async (id: string, range: TimeRange) => {
      const occurrence = byId.get(id);
      if (!occurrence) return;
      if (occurrence.id.startsWith("app:")) {
        try {
          await moveAppEvent(occurrence.id, { start: range.start.toISOString(), end: range.end.toISOString(), all_day: false });
          await data.reload();
        } catch (failure) {
          fail(failure);
        }
        return;
      }
      let scope: Scope = "all";
      if (occurrence.original_start) {
        const chosen = await askScope("edit", ["this", "following", "all"]);
        if (!chosen) return;
        scope = chosen;
      }
      try {
        await updateEvent(
          occurrence.event_id,
          { start: range.start.toISOString(), end: range.end.toISOString(), all_day: false },
          scope,
          occurrence.original_start,
        );
        await data.reload();
      } catch (failure) {
        fail(failure);
      }
    },
    [byId, askScope, data, fail],
  );

  const openOccurrence = React.useCallback((occurrence: Occurrence) => {
    setPending(null);
    setOpened({ kind: "existing", occurrence });
  }, []);

  const jumpTo = React.useCallback(
    (occurrence: Occurrence) => {
      const day = occurrence.all_day ? occurrence.start : dayKey(new Date(occurrence.start));
      if (!visibleDays(shown).includes(day)) {
        go({ view: view === "agenda" ? (mobile ? "three" : "week") : view, day: view === "month" ? `${day.slice(0, 7)}-01` : day });
      }
      openOccurrence(occurrence);
    },
    [shown, view, mobile, go, openOccurrence],
  );

  const toggleLayer = React.useCallback(
    async (layer: Layer) => {
      data.setLayers((all) => all.map((l) => (l.id === layer.id ? { ...l, visible: !l.visible } : l)));
      try {
        await updateLayer(layer.id, { visible: !layer.visible });
      } catch (failure) {
        data.setLayers((all) => all.map((l) => (l.id === layer.id ? layer : l)));
        fail(failure);
      }
    },
    [data, fail],
  );

  const goToday = React.useCallback(() => {
    go({ ...shown, day: view === "month" ? `${today.slice(0, 7)}-01` : today });
  }, [go, shown, view, today]);

  const changeView = React.useCallback((next: View) => go(switchView(shown, next, today)), [go, shown, today]);

  const commands: Command[] = React.useMemo(
    () => [
      { id: "new", label: t("event.new"), icon: "plus", shortcut: "C", run: () => openNew() },
      { id: "today", label: t("cmd.today"), icon: "today", shortcut: "T", run: goToday },
      ...VIEWS.filter((v) => !(mobile && v.value === "week")).map((v) => ({
        id: `view-${v.value}`,
        label: `Ver ${v.label.toLowerCase()}`,
        icon: (v.value === "agenda" ? "list" : "calendar") as Command["icon"],
        shortcut: v.key.toUpperCase(),
        run: () => changeView(v.value),
      })),
      { id: "layer-new", label: t("layer.new"), icon: "layers", run: () => setLayerEdit(null) },
      { id: "subscribe", label: t("subs.title"), icon: "globe", run: () => setSubscribing(true) },
      ...data.layers.map((layer) => ({
        id: `layer-${layer.id}`,
        label: t(layer.visible ? "cmd.hide" : "cmd.show", { name: layer.name }),
        icon: (layer.visible ? "eye-off" : "eye") as Command["icon"],
        run: () => void toggleLayer(layer),
      })),
      ...(!mobile ? [{ id: "sidebar", label: sidebarOpen ? t("cmd.fold") : t("cmd.unfold"), icon: "sidebar" as const, run: () => setSidebarPref(!sidebarOpen) }] : []),
    ],
    [openNew, goToday, changeView, data.layers, toggleLayer, mobile, sidebarOpen, setSidebarPref],
  );

  React.useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPalette((open) => !open);
        return;
      }
      if (palette || scopeAsk || layerEdit !== undefined || subscribing || isTyping(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Escape") {
        if (opened) {
          setOpened(null);
          setPending(null);
        }
        return;
      }
      if (event.key === "/") {
        event.preventDefault();
        setPalette(true);
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "t") goToday();
      else if (event.key === "ArrowLeft") go(step(shown, -1));
      else if (event.key === "ArrowRight") go(step(shown, 1));
      else if (view === "month" && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        event.preventDefault();
        go(scroll(placeRef.current, event.key === "ArrowUp" ? -1 : 1), true);
      }
      else if (key === "c") {
        event.preventDefault();
        openNew();
      } else {
        const found = VIEWS.find((v) => v.key === key);
        if (found && !(mobile && found.value === "week")) changeView(found.value);
        else return;
      }
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [palette, scopeAsk, layerEdit, subscribing, opened, goToday, go, shown, view, openNew, changeView, mobile]);

  const closePanel = () => {
    setOpened(null);
    setPending(null);
  };
  const selectedId = opened?.kind === "existing" ? opened.occurrence.id : null;
  const viewOptions = VIEWS.filter((v) => !(mobile && v.value === "week")).map((v) => ({ value: v.value, label: mobile ? v.short : v.label }));

  const stage = data.loading ? (
    <Skeleton rows={8} label={t("app.loading")} />
  ) : data.failed ? (
    <ErrorState title={t("app.down")} detail={data.error ?? undefined} onRetry={data.reload} />
  ) : view === "month" ? (
      <MonthGrid
        month={`${monthOf(shown)}-01`}
        from={shown.day}
        events={gridEvents}
        now={now}
        selectedId={selectedId}
        onDayClick={(day) => go({ view: "day", day })}
        onEventClick={(id) => {
          const found = byId.get(id);
          if (found) openOccurrence(found);
        }}
        onNavigate={(direction) => go(step(shown, direction))}
        onScroll={(weeks) => go(scroll(placeRef.current, weeks), true)}
      />
    ) : view === "agenda" ? (
      <Agenda
        days={days}
        occurrences={happening}
        layers={layers}
        today={today}
        now={now}
        selectedId={selectedId}
        onOpen={openOccurrence}
        onCreate={() => openNew()}
      />
    ) : (
      <TimeGrid
        label={title}
        days={days}
        events={gridEvents}
        hourHeight={hourHeight}
        onHourHeightChange={setHourHeight}
        selectedId={selectedId}
        pending={pending}
        inlineCreate={!mobile}
        onEventClick={(id) => {
          const found = byId.get(id);
          if (found) openOccurrence(found);
        }}
        onEventChange={onEventChange}
        onCreate={onCreate}
        onDayClick={view === "day" ? undefined : (day) => go({ view: "day", day })}
        onNavigate={(direction) => go(step(shown, direction))}
        onNavigateDays={view === "three" ? (days) => go(step(shown, days)) : undefined}
      />
    );

  const panel = opened && (
    <EventPanel
      opened={opened}
      layers={data.layers}
      presentation={mobile ? "sheet" : "panel"}
      askScope={askScope}
      twin={opened.kind === "existing" ? (twins.get(opened.occurrence.id) ?? null) : null}
      onClose={closePanel}
      onDone={async (message) => {
        await data.reload();
        toast({ message });
      }}
    />
  );

  return (
    <AppShell fill detailLabel="Evento" detail={!mobile && opened ? <div className="cr-detail">{panel}</div> : null}>
      <div className="cr-app" data-sidebar={sidebarOpen || undefined} data-mobile={mobile || undefined}>
        {sidebarOpen && (
          <aside className="cr-sidebar">
            <Sidebar
              layers={data.layers}
              range={days}
              marked={marked}
              today={today}
              onJump={(day) => go({ ...shown, day: view === "month" ? `${day.slice(0, 7)}-01` : day })}
              onCreate={() => openNew()}
              onToggle={(layer) => void toggleLayer(layer)}
              onEditLayer={setLayerEdit}
              onSubscribe={() => setSubscribing(true)}
              onSettings={() => setSettings(true)}
            />
          </aside>
        )}

        <main className="cr-main">
          <header className="cr-toolbar">
            {mobile ? (
              <IconButton icon="layers" label="Capas" variant="plain" onClick={() => setMobileLayers(true)} />
            ) : (
              <IconButton
                icon="sidebar"
                label={sidebarOpen ? t("cmd.fold") : t("cmd.unfold")}
                variant="plain"
                onClick={() => setSidebarPref(!sidebarOpen)}
              />
            )}
            {!mobile && (
              <>
                <Button size="small" variant="secondary" onClick={goToday}>
                  {t("day.today")}
                </Button>
                <div className="cr-arrows">
                  <IconButton icon="chevron-left" label="Anterior" size="small" variant="plain" onClick={() => go(step(shown, -1))} />
                  <IconButton icon="chevron-right" label="Siguiente" size="small" variant="plain" onClick={() => go(step(shown, 1))} />
                </div>
              </>
            )}
            <button
              type="button"
              className="cr-title"
              aria-expanded={mobile ? monthPicker : undefined}
              onClick={() => (mobile ? setMonthPicker((open) => !open) : undefined)}
              tabIndex={mobile ? 0 : -1}
            >
              <span className="cr-title-text">{title}</span>
              {week !== undefined && !mobile && (
              <span className="cr-week">
                <Badge>S{week}</Badge>
              </span>
            )}
              {mobile && <Icon name={monthPicker ? "chevron-up" : "chevron-down"} />}
            </button>
            <div className="cr-toolbar-end">
              {mobile ? (
                <>
                  <Button size="small" variant="secondary" onClick={goToday}>
                    {t("day.today")}
                  </Button>
                  <IconButton icon="search" label="Buscar" variant="plain" onClick={() => setPalette(true)} />
                  <AppHome app="planner" className="cr-home" />
                </>
              ) : (
                <>
                  <button type="button" className="cr-search" onClick={() => setPalette(true)}>
                    <Icon name="search" />
                    <span>Buscar</span>
                    <kbd className="palette-key">⌘K</kbd>
                  </button>
                  <SegmentedControl label={t("app.view")} options={viewOptions} value={view} onChange={changeView} />
                </>
              )}
            </div>
          </header>

          {mobile && (
            <div className="cr-mobile-views">
              <SegmentedControl label={t("app.view")} options={viewOptions} value={view} onChange={changeView} />
            </div>
          )}

          {mobile && monthPicker && (
            <div className="cr-month-picker glass motion-drop-in">
              <MiniMonth
                month={`${view === "month" ? monthOf(shown) : shown.day.slice(0, 7)}-01`}
                range={view === "month" ? [] : days}
                marked={marked}
                onSelect={(day) => {
                  go({ ...shown, day: view === "month" ? `${day.slice(0, 7)}-01` : day });
                  setMonthPicker(false);
                }}
                onMonthChange={(direction) => {
                  const date = dayStart(`${view === "month" ? monthOf(shown) : shown.day.slice(0, 7)}-01`);
                  date.setMonth(date.getMonth() + direction);
                  go({ ...shown, day: dayKey(date) });
                }}
              />
            </div>
          )}

          <OfflineNotice />

          {data.error && !data.failed && (
            <Notice tone="negative" action={{ label: t("action.retry"), onClick: () => void data.reload() }}>
              {t("app.load_failed", { error: data.error ?? "" })}
            </Notice>
          )}

          <div className="cr-stage surface" data-view={view} data-loading={data.loading || undefined}>
            {stage}
          </div>
        </main>

        {mobile && opened && (
          <Sheet title={opened.kind === "new" ? t("event.new") : t("event.event")} onClose={closePanel}>
            {panel}
          </Sheet>
        )}

        {mobile && !opened && (
          <CreateButton label={t("event.event")} onClick={() => openNew()} />
        )}

        {mobile && mobileLayers && (
          <Sheet title={t("app.layers")} onClose={() => setMobileLayers(false)}>
            <Sidebar
              layers={data.layers}
              range={days}
              marked={marked}
              today={today}
              onJump={(day) => {
                go({ ...shown, day: view === "month" ? `${day.slice(0, 7)}-01` : day });
                setMobileLayers(false);
              }}
              onCreate={() => {
                setMobileLayers(false);
                openNew();
              }}
              onToggle={(layer) => void toggleLayer(layer)}
              onEditLayer={(layer) => {
                setMobileLayers(false);
                setLayerEdit(layer);
              }}
              onSubscribe={() => {
                setMobileLayers(false);
                setSubscribing(true);
              }}
              onSettings={() => {
                setMobileLayers(false);
                setSettings(true);
              }}
            />
          </Sheet>
        )}

        {settings && <AppSettingsSheet app={APP} onClose={() => setSettings(false)} />}

        {subscribing && (
          <SubscriptionsSheet
            onClose={() => setSubscribing(false)}
            onSubscribed={(layer) => {
              const already = data.layers.some((one) => one.id === layer.id);
              data.setLayers((all) => [...all.filter((one) => one.id !== layer.id), layer]);
              if (already) {
                toast({ message: t("toast.already", { name: layer.name }) });
                return;
              }
              setAwaiting(layer.id);
              toast({ message: t("toast.arriving", { name: layer.name }) });
            }}
            onUnsubscribed={(layer) => {
              data.setLayers((all) => all.filter((one) => one.id !== layer.id));
              toast({ message: t("toast.unsubscribed", { name: layer.name }) });
            }}
          />
        )}
        {palette && <Palette commands={commands} layers={layers} onOpen={jumpTo} onClose={() => setPalette(false)} />}
        {scopeAsk && <ScopeDialog ask={scopeAsk} />}
        {layerEdit !== undefined && (
          <LayerSheet
            layer={layerEdit}
            layers={data.layers}
            onClose={() => setLayerEdit(undefined)}
            onSave={async (name, tone, display, daysOffFrom) => {
              if (layerEdit) {
                const own = layerEdit.origin === "own";
                const before = (layerEdit.days_off_from ?? []).join();
                const saved = await updateLayer(layerEdit.id, { name, tone, display, ...(own ? { days_off_from: daysOffFrom } : {}) });
                data.setLayers((all) => all.map((l) => (l.id === saved.id ? saved : l)));
                if (own && daysOffFrom.join() !== before) await data.reload();
              } else {
                const created = await createLayer(name, tone, display, daysOffFrom);
                data.setLayers((all) => [...all, created]);
                if (display === "events") setLastLayer(created.id);
              }
              toast({ message: layerEdit ? t("toast.layer_saved") : t("toast.layer_created") });
            }}
          />
        )}

      </div>
    </AppShell>
  );
}

