import { EmptyState, Icon, addDays, dayKey, dayStart, formatClock } from "@openarga/ui";
import * as React from "react";

import type { Layer, Occurrence } from "./api";
import { dateFormat, t } from "./lang";

const dayName = dateFormat({ weekday: "long" });
const dayDate = dateFormat({ day: "numeric", month: "long" });
const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

interface Props {
  days: string[];
  occurrences: Occurrence[];
  layers: Map<string, Layer>;
  today: string;
  now: Date;
  selectedId: string | null;
  onOpen: (occurrence: Occurrence) => void;
  onCreate: () => void;
}

function daysOf(occurrence: Occurrence): [string, string] {
  if (occurrence.all_day) return [occurrence.start, addDays(occurrence.end, -1)];
  const start = new Date(occurrence.start);
  const end = new Date(new Date(occurrence.end).getTime() - 1);
  return [dayKey(start), dayKey(end < start ? start : end)];
}

export function Agenda({ days, occurrences, layers, today, now, selectedId, onOpen, onCreate }: Props) {
  const groups = React.useMemo(() => {
    const byDay = new Map<string, Occurrence[]>(days.map((d) => [d, []]));
    for (const occurrence of occurrences) {
      const [first, last] = daysOf(occurrence);
      for (let day = first; day <= last; day = addDays(day, 1)) byDay.get(day)?.push(occurrence);
    }
    return [...byDay.entries()]
      .filter(([, list]) => list.length > 0)
      .map(([day, list]) => ({
        day,
        list: list.sort((a, b) =>
          a.all_day !== b.all_day ? (a.all_day ? -1 : 1) : a.start.localeCompare(b.start) || a.title.localeCompare(b.title),
        ),
      }));
  }, [days, occurrences]);

  if (groups.length === 0) {
    return (
      <EmptyState
        icon="calendar"
        hue={6}
        title={t("agenda.empty")}
        action={{ label: t("event.new"), icon: "plus", onClick: onCreate }}
      >
        {t("agenda.empty_body")}
      </EmptyState>
    );
  }

  return (
    <div className="cr-agenda">
      {groups.map(({ day, list }) => {
        const date = dayStart(day);
        const label = day === today ? t("day.today") : day === addDays(today, 1) ? t("day.tomorrow") : cap(dayName.format(date));
        return (
          <section
            key={day}
            className="cr-agenda-day"
            data-today={day === today || undefined}
            aria-label={`${label}, ${dayDate.format(date)}`}
          >
            <div className="cr-agenda-head" aria-hidden="true">
              <span className="cr-agenda-number">{date.getDate()}</span>
              <span className="cr-agenda-name">{label}</span>
              <span className="cr-agenda-date">{dayDate.format(date)}</span>
            </div>
            <ul className="cr-agenda-list">
              {list.map((occurrence) => {
                const layer = layers.get(occurrence.calendar_id);
                const past = new Date(occurrence.all_day ? dayStart(occurrence.end) : occurrence.end) <= now;
                const start = new Date(occurrence.start);
                const startsToday = !occurrence.all_day && dayKey(start) === day;
                return (
                  <li key={`${occurrence.id}-${day}`}>
                    <button
                      type="button"
                      className="cr-agenda-row"
                      data-tone={layer?.tone}
                      data-past={past || undefined}
                      data-subscribed={layer?.origin === "subscription" || undefined}
                      data-selected={selectedId === occurrence.id || undefined}
                      onClick={() => onOpen(occurrence)}
                    >
                      <span className="cr-agenda-time">
                        {occurrence.all_day ? t("event.all_day_cap") : startsToday ? formatClock(start) : t("agenda.continues")}
                      </span>
                      <span className="cr-agenda-bar" aria-hidden="true" />
                      <span className="cr-agenda-body">
                        <span className="cr-agenda-title">
                          {occurrence.title}
                          {occurrence.original_start && <Icon name="repeat" />}
                        </span>
                        {(occurrence.location || !occurrence.all_day) && (
                          <span className="cr-agenda-detail">
                            {!occurrence.all_day && `${formatClock(start)} – ${formatClock(new Date(occurrence.end))}`}
                            {!occurrence.all_day && occurrence.location && " · "}
                            {occurrence.location}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
