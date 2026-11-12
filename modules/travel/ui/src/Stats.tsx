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
import { MODES, euros, flag, km, whole } from "./words";

const MONTHS = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

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
        <ScreenHeader title="Cifras" />
        <Pending found={loaded.found} label="Cargando las cifras" />
      </Screen>
    );
  }

  const europe = stats.europe_visited.length;
  const calendar = nightsByMonth(stats.nights_calendar);
  const busiest = Math.max(1, ...[...calendar.values()].flat());

  return (
    <Screen>
      <ScreenHeader title="Cifras" />
      {stats.trips === 0 && (
        <EmptyState
          icon="chart"
          title="Aún no hay cifras"
          action={{ label: "Añadir un viaje", icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }}
        >
          Salen de los viajes hechos: países, noches, kilómetros y lo que costaron.
        </EmptyState>
      )}

      <StatRow label="Resumen">
        <StatTile
          label="Europa"
          value={`${europe} de ${stats.europe_total}`}
          progress={europe / stats.europe_total}
          foot={stats.europe_visited.map(flag).join(" ") || "Ninguno todavía"}
          info="Los 44 estados de Europa de la ONU donde has dormido o que has visitado."
        />
        <StatTile label="Países" value={whole(stats.countries)} foot={`${whole(stats.regions)} regiones`} />
        <StatTile label="Noches fuera" value={whole(stats.nights)} foot={`${whole(stats.trips)} viajes`} />
        <StatTile
          label="Kilómetros"
          value={whole(stats.km)}
          info="El avión, en línea recta. Tren, coche, bus y barco, una estimación sobre la línea recta: no se traza la carretera."
        />
        <StatTile
          label="Coste medio al día"
          value={stats.average_cost_per_day !== null ? euros(stats.average_cost_per_day) : "—"}
          foot="por persona"
          info="La media del coste por día de cada viaje con gastos: lo que costó por persona entre sus días, contando el primero y el último."
        />
      </StatRow>

      {stats.by_year.length > 0 && (
        <section className="surface travel-panel">
          <Heading>Por año</Heading>
          <SeriesChart
            label="Viajes y noches fuera por año"
            labels={stats.by_year.map((row) => String(row.year))}
            series={[
              { key: "nights", name: "Noches", values: stats.by_year.map((row) => row.nights) },
              { key: "trips", name: "Viajes", values: stats.by_year.map((row) => row.trips) },
            ]}
            order={["nights", "trips"]}
            format={whole}
          />
        </section>
      )}

      {stats.km > 0 && (
        <section className="surface travel-panel">
          <Heading>Kilómetros por medio</Heading>
          <ShareChart
            label="Kilómetros por medio de transporte"
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
          <Heading>Los países que más repites</Heading>
          <DataTable
            label="Países por número de viajes"
            rowKey={(row) => row.code}
            rows={stats.top_countries}
            columns={[
              { key: "name", label: "País", cell: (row) => `${flag(row.code)} ${row.name}` },
              { key: "trips", label: "Viajes", numeric: true, cell: (row) => whole(row.trips) },
              { key: "nights", label: "Noches", numeric: true, cell: (row) => whole(row.nights) },
            ]}
          />
        </section>
      )}

      {stats.cost_per_day.length > 0 && (
        <section className="surface travel-panel">
          <Heading>Coste por día de cada viaje</Heading>
          <DataTable
            label="Coste por día y por persona de cada viaje"
            rowKey={(row) => row.trip_id}
            rows={[...stats.cost_per_day].reverse()}
            onRowClick={(row) => navigate({ screen: "trip", id: row.trip_id })}
            columns={[
              { key: "title", label: "Viaje", cell: (row) => row.title },
              { key: "year", label: "Año", cell: (row) => row.starts_on.slice(0, 4) },
              { key: "per_day", label: "Al día", numeric: true, cell: (row) => euros(row.per_day) },
            ]}
            footer={[
              "Media",
              "",
              stats.average_cost_per_day !== null ? euros(stats.average_cost_per_day) : "—",
            ]}
          />
        </section>
      )}

      {stats.spend_per_night_by_country.length > 0 && (
        <section className="surface travel-panel">
          <Heading>Gasto por noche en cada país</Heading>
          <DataTable
            label="Gasto por persona y noche en cada país"
            rowKey={(row) => row.code}
            rows={stats.spend_per_night_by_country}
            columns={[
              { key: "name", label: "País", cell: (row) => `${flag(row.code)} ${row.name}` },
              { key: "nights", label: "Noches", numeric: true, cell: (row) => whole(row.nights) },
              { key: "per_night", label: "Por noche", numeric: true, cell: (row) => euros(row.per_night) },
            ]}
          />
          <p className="travel-footnote">
            Todo el gasto del viaje por persona, repartido entre sus países según las noches dormidas en cada uno.
          </p>
        </section>
      )}

      {calendar.size > 0 && (
        <section className="surface travel-panel">
          <Heading>Noches fuera, mes a mes</Heading>
          <table className="travel-calendar">
            <thead>
              <tr>
                <th scope="col">
                  <span className="visually-hidden">Año</span>
                </th>
                {MONTHS.map((month, index) => (
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
                      title={`${count} noches`}
                    >
                      <span className="visually-hidden">{count} noches</span>
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
