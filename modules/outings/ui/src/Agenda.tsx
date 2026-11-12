import { EmptyState, Hint, IconBadge, List, ListRow, MonthCalendar, OfflineNotice, Screen, Section } from "@openarga/ui";
import type { AreaPoint } from "@openarga/ui/area-map";
import { Suspense, lazy, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type AgendaEvent, readMine } from "./api";
import { VIEW, useMapBase } from "./area";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { categoryOf, dayTitle, eventLine, isoDay, longDay, marksOf, monthName, onDay, shortDay, span, until } from "./words";

const AreaMap = lazy(() => import("@openarga/ui/area-map").then((found) => ({ default: found.AreaMap })));

const pad = (value: number) => String(value).padStart(2, "0");

export function monthSpan(year: number, month: number): [string, string] {
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return [`${year}-${pad(month + 1)}-01`, `${year}-${pad(month + 1)}-${pad(last)}`];
}

export function AgendaScreen({
  onOpen,
  onOpenId,
  onExplore,
}: {
  onOpen: (event: AgendaEvent) => void;
  onOpenId: (id: string) => void;
  onExplore: () => void;
}) {
  const today = isoDay(new Date());
  const [year, setYear] = useState(() => Number(today.slice(0, 4)));
  const [month, setMonth] = useState(() => Number(today.slice(5, 7)) - 1);
  const [selected, setSelected] = useState(today);
  const [first, last] = monthSpan(year, month);
  const { data: mine, found } = useLoad(`mine:${first}`, () => readMine(first, last));
  const until_ = isoDay(new Date(Date.now() + 120 * 86_400_000));
  const { data: ahead, found: aheadFound } = useLoad("coming", () => readMine(today, until_));
  const coming = ahead?.events ?? null;
  const both = {
    error: found.error ?? aheadFound.error,
    refresh: () => Promise.all([found.refresh(), aheadFound.refresh()]).then(() => undefined),
  };

  function move(step: number) {
    const next = new Date(Date.UTC(year, month + step, 1));
    setYear(next.getUTCFullYear());
    setMonth(next.getUTCMonth());
    setSelected(isoDay(next));
  }

  const events = mine?.events ?? [];
  const thatDay = onDay(events, selected);
  const base = useMapBase();
  const located = events.filter((one) => one.lat != null && one.lon != null);
  const points: AreaPoint[] = located.map((one) => ({
    id: one.id,
    lon: one.lon!,
    lat: one.lat!,
    kind: "pill",
    label: shortDay(one.starts_on),
    hue: categoryOf(one.category).hue,
    title: one.title,
  }));
  const empty = coming !== null && coming.length === 0;

  return (
    <Screen>
      <ScreenHeader eyebrow={longDay(today)} title="Agenda" />

      <OfflineNotice />

      <MonthCalendar
        year={year}
        month={month}
        marks={marksOf(events)}
        today={today}
        selected={selected}
        onSelect={setSelected}
        onPrevious={() => move(-1)}
        onNext={() => move(1)}
      />

      {(mine === null || (coming === null && both.error)) && <Pending found={both} rows={2} />}
      {mine !== null && (
        <Section title={selected === today ? "Hoy" : dayTitle(selected, true)} count={thatDay.length || undefined}>
          {thatDay.length > 0 ? (
            <List>
              {thatDay.map((event) => (
                <EventRow key={event.id} event={event} onOpen={() => onOpen(event)} />
              ))}
            </List>
          ) : (
            <Hint>Nada tuyo este día.</Hint>
          )}
        </Section>
      )}

      {base && points.length > 0 && (
        <Section title={`Dónde, en ${monthName(month + 1)}`}>
          <div className="outings-month-map">
            <Suspense fallback={null}>
              <AreaMap
                base={base}
                view={VIEW[located.some((one) => one.zone === "region") ? "region" : "near"]}
                points={points}
                onSelect={(id) => id && onOpenId(id)}
                label={`Dónde es lo tuyo en ${monthName(month + 1)}`}
              />
            </Suspense>
          </div>
        </Section>
      )}

      {empty && (
        <EmptyState icon="calendar" title="Tu agenda está vacía" action={{ label: "Explorar", onClick: onExplore }}>
          Busca en Explorar: lo que guardes con Me apetece o mandes a Planner sale aquí, en su día y en el mapa.
        </EmptyState>
      )}

      {coming !== null && coming.length > 0 && (
        <Section title="Lo próximo" count={coming.length}>
          <List>
            {coming.slice(0, 8).map((event) => (
              <EventRow key={event.id} event={event} withDay onOpen={() => onOpen(event)} />
            ))}
          </List>
        </Section>
      )}

      <AppVersion />
    </Screen>
  );
}

export function EventRow({
  event,
  onOpen,
  withDay = false,
  day,
  reason,
}: {
  event: AgendaEvent;
  onOpen: () => void;
  withDay?: boolean;
  day?: string;
  reason?: string;
}) {
  const category = categoryOf(event.category);
  const when = day ?? (withDay ? span(event) : undefined);
  return (
    <ListRow
      title={event.title}
      subtitle={[when, reason ?? eventLine(event)].filter(Boolean).join(" · ") || undefined}
      icon={category.icon}
      hue={category.hue}
      value={event.time ?? undefined}
      detail={event.in_calendar ? "En Planner" : event.wish_id ? "Guardado" : event.highlight ? "Destacado" : undefined}
      onClick={onOpen}
    />
  );
}

export function NowCard({ event, onOpen }: { event: AgendaEvent; onOpen: () => void }) {
  const category = categoryOf(event.category);
  return (
    <button type="button" className="surface outings-now" onClick={onOpen}>
      <span className="outings-now-band" data-hue={category.hue}>
        <IconBadge name={category.icon} hue={category.hue} />
        <span className="outings-now-tag">{[category.label, until(event)].filter(Boolean).join(" · ")}</span>
      </span>
      <span className="outings-now-text">
        <span className="outings-now-title">{event.title}</span>
        {(event.town || event.summary) && (
          <span className="outings-card-line">{[event.town, event.summary].filter(Boolean).join(" · ")}</span>
        )}
      </span>
    </button>
  );
}
