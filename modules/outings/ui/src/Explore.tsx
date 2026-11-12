import { Button, ChoiceChips, EmptyState, Hint, List, OfflineNotice, Screen, SearchField, Section, SegmentedControl } from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { EventRow } from "./Agenda";
import { AppVersion } from "./AppVersion";
import { type AgendaEvent, type Category, type When, Unauthorised, readExplore, readForYou, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { UpdateSheet } from "./UpdateSheet";
import { CATEGORIES, WHENS, ZONES, type ZoneFilter, dayTitle, freshSince, freshTitle, isoDay, monthTitle } from "./words";

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
  const fromNotice = arrived.has("nuevo") || arrived.has("cuando");
  const noticeWhen = WHENS.find((one) => one.value === arrived.get("cuando"))?.value;
  const [query, setQuery] = useState(fromNotice ? "" : kept.typed.trim());
  const [typed, setTyped] = useState(fromNotice ? "" : kept.typed);
  const [when, setWhen] = useState<When>(noticeWhen ?? (fromNotice ? "quarter" : kept.when));
  const [zone, setZone] = useState<ZoneFilter>(fromNotice ? "all" : kept.zone);
  const [filter, setFilter] = useState<Filter>(fromNotice ? "all" : kept.filter);
  const [byDate, setByDate] = useState(fromNotice ? false : kept.byDate);
  const today = isoDay(new Date());
  const fresh = freshSince(arrived.get("nuevo"), today);
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
    setProblem(error instanceof Error ? error.message : "No se ha podido buscar.");
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
      <ScreenHeader eyebrow="Pamplona y Navarra" title="Explorar" />

      <SearchField value={typed} onChange={setTyped} placeholder="Jazz, Baluarte, setas, Olite…" label="Buscar en la agenda" />
      <SegmentedControl label="Cuándo" options={WHENS} value={when} onChange={setWhen} />
      <ChoiceChips label="Dónde" options={ZONES} value={zone} onChange={setZone} scroll />
      <ChoiceChips
        label="Qué"
        scroll
        options={[{ value: "all" as Filter, label: "Todo" }, ...CATEGORIES.map(({ value, label }) => ({ value: value as Filter, label }))]}
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
            !allFresh && arrivals!.total > newOnes.length ? { label: `Ver los ${arrivals!.total}`, onClick: () => setAllFresh(true) } : undefined
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
        <Hint>Lo que trajo el aviso ya pasó o lo apartaste.</Hint>
      )}

      {!narrowed && forYou.length > 0 && (
        <Section title="Para ti" count={forYou.length}>
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
          title="La agenda está vacía"
          action={{ label: "Actualizar", onClick: () => setUpdating(true) }}
        >
          La llena tu Claude: en Actualizar se copia el encargo, o lo hace solo la tarea de cada semana.
        </EmptyState>
      )}
      {found !== null && found.total === 0 && narrowed && <Hint>Nada con eso en estas fechas. Prueba con más tiempo.</Hint>}

      {found !== null && found.total > 0 && sort === "best" && (
        <Section
          title="Lo destacado"
          count={found.total}
          action={{ label: "Por fecha", onClick: () => setByDate(true) }}
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
                Lo destacado primero
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
          Ver {Math.min(left, PAGE)} más de {found!.total}
        </Button>
      )}

      <div className="outings-actions">
        <Button variant="plain" icon="repeat" onClick={() => setUpdating(true)}>
          Actualizar
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
