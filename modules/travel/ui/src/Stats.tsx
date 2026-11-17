import {
  DataTable,
  EmptyState,
  Heading,
  Screen,
  SeriesChart,
  ShareChart,
  StatRow,
  StatTile,
} from "@openarga/ui";
import type { CSSProperties } from "react";

import { type Mode, type Stats, type Trip, readStats } from "./api";
import type { Navigate } from "./App";
import { AppVersion } from "./AppVersion";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { MODES, euros, flag, km, nights, whole } from "./words";
import { intl, plural, t } from "./lang";

const monthNarrow = (month: number) =>
  new Intl.DateTimeFormat(intl(), { month: "narrow", timeZone: "UTC" }).format(new Date(Date.UTC(2000, month - 1, 1))).toUpperCase();

export function nightsByMonth(calendar: Record<string, number>): Map<number, number[]> {
  const years = new Map<number, number[]>();
  for (const [day, count] of Object.entries(calendar)) {
    const year = Number(day.slice(0, 4));
    const month = Number(day.slice(5, 7)) - 1;
    const row = years.get(year) ?? Array.from({ length: 12 }, () => 0);
    row[month] = (row[month] ?? 0) + count;
    years.set(year, row);
  }
  return new Map([...years.entries()].sort(([a], [b]) => b - a));
}

export function StatsScreen({ navigate }: { trips: Trip[] | null; navigate: Navigate }) {
  const loaded = useLoad<Stats>("stats", readStats);
  const stats = loaded.data;

  if (!stats) {
    return (
      <Screen>
        <ScreenHeader title={t("stats.title")} />
        <Pending found={loaded.found} label={t("stats.loading")} />
      </Screen>
    );
  }

  const europe = stats.europe_visited.length;
  const calendar = nightsByMonth(stats.nights_calendar);
  const busiest = Math.max(1, ...[...calendar.values()].flat());

  return (
    <Screen>
      <ScreenHeader title={t("stats.title")} />
      {stats.trips === 0 && (
        <EmptyState
          icon="chart"
          title={t("stats.empty")}
          action={{ label: t("stats.add_trip"), icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
        >
          {t("stats.empty_detail")}
        </EmptyState>
      )}

      <StatRow label={t("trip.summary")}>
        <StatTile
          label={t("stats.europe")}
          value={t("stats.of", { count: europe, total: stats.europe_total })}
          progress={europe / stats.europe_total}
          foot={stats.europe_visited.map(flag).join(" ") || t("stats.none_yet")}
          info={t("stats.europe_info")}
        />
        <StatTile label={t("stats.countries")} value={whole(stats.countries)} foot={plural(stats.regions, "count.regions", { count: whole(stats.regions) })} />
        <StatTile label={t("stats.nights_away")} value={whole(stats.nights)} foot={plural(stats.trips, "count.trips", { count: whole(stats.trips) })} />
        <StatTile
          label={t("stats.km")}
          value={whole(stats.km)}
          info={t("stats.km_info")}
        />
        <StatTile
          label={t("stats.cost_per_day")}
          value={stats.average_cost_per_day !== null ? euros(stats.average_cost_per_day) : "—"}
          foot={t("stats.per_person")}
          info={t("stats.cost_info")}
        />
      </StatRow>

      {stats.by_year.length > 0 && (
        <section className="surface travel-panel">
          <Heading>{t("stats.by_year")}</Heading>
          <SeriesChart
            label={t("stats.by_year_label")}
            labels={stats.by_year.map((row) => String(row.year))}
            series={[
              { key: "nights", name: t("stats.nights"), values: stats.by_year.map((row) => row.nights) },
              { key: "trips", name: t("nav.trips"), values: stats.by_year.map((row) => row.trips) },
            ]}
            order={["nights", "trips"]}
            format={whole}
          />
        </section>
      )}

      {stats.km > 0 && (
        <section className="surface travel-panel">
          <Heading>{t("stats.km_by_mode")}</Heading>
          <ShareChart
            label={t("stats.km_by_mode_label")}
            items={(Object.keys(stats.km_by_mode) as Mode[]).map((mode) => ({
              key: mode,
              name: MODES[mode].label,
              value: stats.km_by_mode[mode],
            }))}
            order={Object.keys(MODES)}
            format={km}
            center={km(stats.km)}
          />
        </section>
      )}

      {stats.top_countries.length > 0 && (
        <section className="surface travel-panel">
          <Heading>{t("stats.top_countries")}</Heading>
          <DataTable
            label={t("stats.top_countries_label")}
            rowKey={(row) => row.code}
            rows={stats.top_countries}
            columns={[
              { key: "name", label: t("stats.country"), cell: (row) => `${flag(row.code)} ${row.name}` },
              { key: "trips", label: t("nav.trips"), numeric: true, cell: (row) => whole(row.trips) },
              { key: "nights", label: t("stats.nights"), numeric: true, cell: (row) => whole(row.nights) },
            ]}
          />
        </section>
      )}

      {stats.cost_per_day.length > 0 && (
        <section className="surface travel-panel">
          <Heading>{t("stats.cost_by_trip")}</Heading>
          <DataTable
            label={t("stats.cost_by_trip_label")}
            rowKey={(row) => row.trip_id}
            rows={[...stats.cost_per_day].reverse()}
            onRowClick={(row) => navigate({ screen: "trip", id: row.trip_id })}
            columns={[
              { key: "title", label: t("trip.title"), cell: (row) => row.title },
              { key: "year", label: t("stats.year"), cell: (row) => row.starts_on.slice(0, 4) },
              { key: "per_day", label: t("stats.a_day"), numeric: true, cell: (row) => euros(row.per_day) },
            ]}
            footer={[
              t("stats.average"),
              "",
              stats.average_cost_per_day !== null ? euros(stats.average_cost_per_day) : "—",
            ]}
          />
        </section>
      )}

      {stats.spend_per_night_by_country.length > 0 && (
        <section className="surface travel-panel">
          <Heading>{t("stats.night_cost")}</Heading>
          <DataTable
            label={t("stats.night_cost_label")}
            rowKey={(row) => row.code}
            rows={stats.spend_per_night_by_country}
            columns={[
              { key: "name", label: t("stats.country"), cell: (row) => `${flag(row.code)} ${row.name}` },
              { key: "nights", label: t("stats.nights"), numeric: true, cell: (row) => whole(row.nights) },
              { key: "per_night", label: t("stats.per_night"), numeric: true, cell: (row) => euros(row.per_night) },
            ]}
          />
          <p className="travel-footnote">
            {t("stats.night_cost_note")}
          </p>
        </section>
      )}

      {calendar.size > 0 && (
        <section className="surface travel-panel">
          <Heading>{t("stats.month_by_month")}</Heading>
          <table className="travel-calendar">
            <thead>
              <tr>
                <th scope="col">
                  <span className="visually-hidden">{t("stats.year")}</span>
                </th>
                {Array.from({ length: 12 }, (_, index) => monthNarrow(index + 1)).map((month, index) => (
                  <th key={index} scope="col">
                    {month}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...calendar.entries()].map(([year, months]) => (
                <tr key={year}>
                  <th scope="row">{year}</th>
                  {months.map((count, index) => (
                    <td
                      key={index}
                      className="travel-calendar-cell"
                      data-empty={count === 0 || undefined}
                      style={{ "--level": `${Math.round(Math.sqrt(count / busiest) * 100)}%` } as CSSProperties}
                      title={nights(count)}
                    >
                      <span className="visually-hidden">{nights(count)}</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <AppVersion />
    </Screen>
  );
}
