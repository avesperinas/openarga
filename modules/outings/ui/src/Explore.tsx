import { Button, ChoiceChips, EmptyState, Hint, List, OfflineNotice, Screen, SearchField, Section, SegmentedControl } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { EventRow } from "./Agenda";
import { AppVersion } from "./AppVersion";
import { useArea } from "./area";
import { type AgendaEvent, type Category, type When, Unauthorised, readExplore, readForYou, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { UpdateSheet } from "./UpdateSheet";
import { dayIn, t } from "./lang";
import { WHEN_VALUES, type ZoneFilter, categories, dayTitle, freshSince, freshTitle, monthTitle, whens, zones } from "./words";

type Filter = "all" | Category;

const PAGE = 40;
const FOR_YOU = 5;
const FRESH = 5;

const kept: { typed: string; when: When; zone: ZoneFilter; filter: Filter; byDate: boolean } = {
  typed: "",
  when: "quarter",
  zone: "all",
  filter: "all",
  byDate: false,
};

export function ExploreScreen({ onOpen }: { onOpen: (event: AgendaEvent) => void }) {
  const [arrived] = useState(() => new URLSearchParams(window.location.search));
  const area = useArea();
  const fromNotice = arrived.has("new") || arrived.has("when");
  const noticeWhen = WHEN_VALUES.find((one) => one === arrived.get("when"));
  const [query, setQuery] = useState(fromNotice ? "" : kept.typed.trim());
  const [typed, setTyped] = useState(fromNotice ? "" : kept.typed);
  const [when, setWhen] = useState<When>(noticeWhen ?? (fromNotice ? "quarter" : kept.when));
  const [zone, setZone] = useState<ZoneFilter>(fromNotice ? "all" : kept.zone);
  const [filter, setFilter] = useState<Filter>(fromNotice ? "all" : kept.filter);
  const [byDate, setByDate] = useState(fromNotice ? false : kept.byDate);
  const today = dayIn(new Date());
  const fresh = freshSince(arrived.get("new"), today);
  const [allFresh, setAllFresh] = useState(fresh.fromNotice);

  useEffect(() => {
    Object.assign(kept, { typed, when, zone, filter, byDate });
  }, [typed, when, zone, filter, byDate]);
  const [more, setMore] = useState<AgendaEvent[]>([]);
  const [problem, setProblem] = useState("");
  const [updating, setUpdating] = useState(false);
  const { data: picks } = useLoad("foryou", readForYou);
  const { data: arrivals } = useLoad(`fresh:${fresh.since}:${allFresh}`, () =>
    readExplore({ when: "year", since: fresh.since, sort: "best", limit: allFresh ? PAGE : FRESH }),
  );
  const newOnes = arrivals?.events ?? [];
  const shownNew = new Set(newOnes.map((one) => one.id));
  const forYou = (picks ?? []).filter((pick) => !shownNew.has(pick.event.id));

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : t("problem.search"));
  }, []);

  useEffect(() => {
    const later = window.setTimeout(() => setQuery(typed.trim()), 250);
    return () => window.clearTimeout(later);
  }, [typed]);

  const narrowed = query !== "" || filter !== "all" || zone !== "all";
  const sort = narrowed || byDate ? "date" : "best";

  const ask = useCallback(
    (offset: number) =>
      readExplore({
        q: query || undefined,
        when,
        zone: zone === "all" ? undefined : zone,
        category: filter === "all" ? undefined : filter,
        sort,
        limit: PAGE,
        offset,
      }),
    [query, when, zone, filter, sort],
  );

  const key = `explore:${JSON.stringify([query, when, zone, filter, sort])}`;
  const { data: found, found: asked } = useLoad(key, () => ask(0));

  useEffect(() => {
    setMore([]);
    setProblem("");
  }, [key]);

  async function next() {
    if (!found) return;
    try {
      const page = await ask(found.events.length + more.length);
      setMore((before) => [...before, ...page.events]);
    } catch (error) {
      fail(error);
    }
  }

  const events = found ? [...found.events, ...more] : [];
  const left = found ? found.total - events.length : 0;

  return (
    <Screen>
      <ScreenHeader eyebrow={area ? `${area.name} · ${area.region}` : undefined} title={t("tab.explore")} />

      <SearchField value={typed} onChange={setTyped} placeholder={t("explore.placeholder")} label={t("explore.search")} />
      <SegmentedControl label={t("explore.when")} options={whens()} value={when} onChange={setWhen} />
      <ChoiceChips label={t("explore.where")} options={zones(area)} value={zone} onChange={setZone} scroll />
      <ChoiceChips
        label={t("explore.what")}
        scroll
        options={[{ value: "all" as Filter, label: t("filter.all") }, ...categories().map(({ value, label }) => ({ value: value as Filter, label }))]}
        value={filter}
        onChange={setFilter}
      />

      <OfflineNotice />
      {problem && <Hint tone="warning">{problem}</Hint>}

      {!narrowed && newOnes.length > 0 && (
        <Section
          title={freshTitle(fresh.since, fresh.fromNotice, today)}
          count={arrivals!.total}
          action={
            !allFresh && arrivals!.total > newOnes.length ? { label: t("explore.see_all", { count: arrivals!.total }), onClick: () => setAllFresh(true) } : undefined
          }
        >
          <List>
            {newOnes.map((event) => (
              <EventRow key={event.id} event={event} withDay onOpen={() => onOpen(event)} />
            ))}
          </List>
        </Section>
      )}
      {fresh.fromNotice && arrivals && arrivals.total === 0 && !narrowed && (
        <Hint>{t("explore.notice_gone")}</Hint>
      )}

      {!narrowed && forYou.length > 0 && (
        <Section title={t("explore.for_you")} count={forYou.length}>
          <List>
            {forYou.slice(0, FOR_YOU).map((pick) => (
              <EventRow
                key={pick.event.id}
                event={pick.event}
                withDay
                reason={pick.reasons[0]}
                onOpen={() => onOpen(pick.event)}
              />
            ))}
          </List>
        </Section>
      )}

      {found === null && <Pending found={asked} rows={5} />}

      {found !== null && found.total === 0 && !narrowed && (
        <EmptyState
          icon="search"
          title={t("explore.empty")}
          action={{ label: t("action.update"), onClick: () => setUpdating(true) }}
        >
          {t("explore.empty_body")}
        </EmptyState>
      )}
      {found !== null && found.total === 0 && narrowed && <Hint>{t("explore.nothing")}</Hint>}

      {found !== null && found.total > 0 && sort === "best" && (
        <Section
          title={t("explore.best")}
          count={found.total}
          action={{ label: t("explore.by_date"), onClick: () => setByDate(true) }}
        >
          <List>
            {events
              .filter((event) => !shownNew.has(event.id))
              .map((event) => (
                <EventRow key={event.id} event={event} withDay onOpen={() => onOpen(event)} />
              ))}
          </List>
        </Section>
      )}

      {found !== null && found.total > 0 && sort === "date" && (
        <>
          {!narrowed && (
            <div className="outings-actions">
              <Button variant="plain" icon="filter" onClick={() => setByDate(false)}>
                {t("explore.best_first")}
              </Button>
            </div>
          )}
          {byMonth(events, found.first).map(({ month, days }) => (
            <Section key={month} title={monthTitle(month)}>
              {days.map(({ day, events: those }) => (
                <List key={day}>
                  {those.map((event) => (
                    <EventRow key={event.id} event={event} day={dayTitle(day)} onOpen={() => onOpen(event)} />
                  ))}
                </List>
              ))}
            </Section>
          ))}
        </>
      )}

      {left > 0 && (
        <Button variant="secondary" onClick={() => void next()}>
          {t("explore.more", { count: Math.min(left, PAGE), total: found!.total })}
        </Button>
      )}

      <div className="outings-actions">
        <Button variant="plain" icon="repeat" onClick={() => setUpdating(true)}>
          {t("action.update")}
        </Button>
      </div>

      <AppVersion />

      {updating && <UpdateSheet onClose={() => setUpdating(false)} />}
    </Screen>
  );
}

export function byMonth(
  events: AgendaEvent[],
  first: string,
): { month: string; days: { day: string; events: AgendaEvent[] }[] }[] {
  const months = new Map<string, Map<string, AgendaEvent[]>>();
  for (const event of events) {
    const day = event.starts_on < first ? first : event.starts_on;
    const month = `${day.slice(0, 7)}-01`;
    const days = months.get(month) ?? new Map<string, AgendaEvent[]>();
    days.set(day, [...(days.get(day) ?? []), event]);
    months.set(month, days);
  }
  return [...months.entries()].map(([month, days]) => ({
    month,
    days: [...days.entries()].map(([day, found]) => ({ day, events: found })),
  }));
}
