import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../calendar.css";

import {
  type CalendarEvent,
  MiniMonth,
  MonthGrid,
  TimeGrid,
  type TimeRange,
  addDays,
  dayRange,
  mondayOf,
} from "../src/index";

const meta: Meta = { title: "Calendario/Rejilla", parameters: { layout: "fullscreen" }, excludeStories: ["WEEK"] };
export default meta;

const NOW = new Date(2026, 8, 30, 11, 20);
const MONDAY = "2026-09-28";

const at = (day: number, time: string) => {
  const [h, m] = time.split(":").map(Number) as [number, number];
  const date = new Date(2026, 8, 28 + day, h, m);
  return date.toISOString();
};

let next = 0;
const ev = (day: number, from: string, to: string, title: string, tone: CalendarEvent["tone"], extra: Partial<CalendarEvent> = {}): CalendarEvent => ({
  id: `e${next++}`,
  title,
  start: at(day, from),
  end: at(day, to),
  tone,
  ...extra,
});

export const WEEK: CalendarEvent[] = [
  ev(0, "08:00", "08:45", "Correr por el río", 2, { recurring: true }),
  ev(0, "09:30", "10:00", "Planificación semanal", 1, { recurring: true }),
  ev(0, "10:00", "12:00", "Bloque de concentración", 8),
  ev(0, "11:00", "11:30", "Llamada con el taller", 9, { subtitle: "Por teléfono" }),
  ev(0, "13:30", "14:30", "Comida con Ane", 7, { subtitle: "Café Iruña" }),
  ev(0, "19:00", "20:00", "Inglés", 5, { recurring: true, subtitle: "Study 3" }),
  ev(1, "09:00", "10:00", "Revisión de diseño", 1),
  ev(1, "09:00", "09:30", "Standup", 6, { recurring: true }),
  ev(1, "09:15", "10:30", "Entrevista", 4),
  ev(1, "12:00", "12:15", "Pagar el seguro", 3),
  ev(1, "16:00", "17:30", "Dentista", 4, { subtitle: "Calle Mayor 12" }),
  ev(1, "22:00", "23:59", "Final de Champions", 2, { subscribed: true }),
  ev(2, "07:30", "08:15", "Gimnasio", 2, { recurring: true }),
  ev(2, "10:00", "11:00", "Tutoría", 5, { status: "cancelled" }),
  ev(2, "11:00", "12:30", "Taller de escritura", 10),
  ev(2, "12:00", "13:00", "Reunión de equipo", 1),
  ev(2, "12:15", "12:45", "Café con Iñaki", 7),
  ev(2, "15:00", "16:00", "Recoger paquete", 3, { status: "tentative" }),
  ev(2, "18:30", "20:00", "Pádel", 6),
  ev(3, "08:00", "08:45", "Correr por el río", 2, { recurring: true }),
  ev(3, "09:00", "13:00", "Examen de estadística", 4, { subtitle: "Edificio Las Encinas" }),
  ev(3, "19:00", "20:00", "Inglés", 5, { recurring: true, subtitle: "Study 3" }),
  ev(3, "21:30", "23:00", "Cena de cumpleaños", 7),
  ev(4, "09:00", "09:30", "Standup", 6, { recurring: true }),
  ev(4, "10:00", "10:10", "Tomar la pastilla", 8),
  ev(4, "10:10", "10:20", "Regar las plantas", 2),
  ev(4, "15:00", "18:00", "Mudanza de Leire", 9),
  ev(4, "23:00", "23:59", "Tren nocturno", 6),
  ev(5, "00:00", "07:40", "Tren nocturno", 6, { subtitle: "Llega a Madrid" }),
  ev(5, "11:00", "13:00", "Shopping de la Plaza", 3),
  ev(5, "14:00", "16:00", "GP de Singapur · carrera", 4, { subscribed: true }),
  ev(6, "10:00", "11:30", "Monte: Ezkaba", 2),
  ev(6, "17:00", "19:00", "Osasuna – Betis", 4, { subscribed: true }),
  { id: "h1", title: "Fiesta local", start: "2026-09-29", end: "2026-09-30", allDay: true, tone: 4, subscribed: true },
  { id: "v1", title: "Viaje a Lisboa", start: "2026-10-01", end: "2026-10-05", allDay: true, tone: 6 },
  { id: "c1", title: "Congreso", start: "2026-09-26", end: "2026-09-30", allDay: true, tone: 5 },
  { id: "b1", title: "Cumpleaños de Ama", start: "2026-10-02", end: "2026-10-03", allDay: true, tone: 7, recurring: true },
  { id: "d1", title: "Declaración trimestral", start: "2026-09-30", end: "2026-10-01", allDay: true, tone: 3 },
  { id: "x1", title: "Semana de la movilidad", start: "2026-09-28", end: "2026-10-04", allDay: true, tone: 8, subscribed: true },
];

function useEvents(initial: CalendarEvent[]) {
  const [events, setEvents] = React.useState(initial);
  const change = (id: string, range: TimeRange) =>
    new Promise<void>((resolve) =>
      setTimeout(() => {
        setEvents((all) => all.map((e) => (e.id === id ? { ...e, start: range.start.toISOString(), end: range.end.toISOString() } : e)));
        resolve();
      }, 250),
    );
  const create = (range: TimeRange & { allDay?: boolean }, title?: string) =>
    setEvents((all) => [
      ...all,
      {
        id: `n${all.length}`,
        title: title ?? "Nuevo evento",
        start: range.allDay ? range.start.toISOString().slice(0, 10) : range.start.toISOString(),
        end: range.allDay ? range.end.toISOString().slice(0, 10) : range.end.toISOString(),
        allDay: range.allDay,
        tone: 1,
      },
    ]);
  return { events, change, create };
}

function Frame({ children, height = "calc(100vh - 2 * var(--space-8))" }: { children: React.ReactNode; height?: string }) {
  return (
    <div
      className="surface"
      style={{ height, overflow: "hidden", borderRadius: "var(--radius-surface)", boxShadow: "var(--elevation-rest)" }}
    >
      {children}
    </div>
  );
}

function Grid({ days, count }: { days?: string[]; count: number }) {
  const { events, change, create } = useEvents(WEEK);
  const [first, setFirst] = React.useState(count === 7 ? MONDAY : "2026-09-29");
  const [selected, setSelected] = React.useState<string | null>(null);
  const [height, setHeight] = React.useState(48);
  return (
    <Frame>
      <TimeGrid
        label="Semana de prueba"
        days={days ?? dayRange(first, count)}
        events={events}
        now={NOW}
        weekNumber={count === 7}
        hourHeight={height}
        onHourHeightChange={setHeight}
        selectedId={selected}
        onEventClick={(id) => setSelected((current) => (current === id ? null : id))}
        onEventChange={change}
        onCreate={create}
        inlineCreate
        onNavigate={(step) => setFirst((day) => addDays(day, step * count))}
        onNavigateDays={count === 3 ? (days) => setFirst((day) => addDays(day, days)) : undefined}
      />
    </Frame>
  );
}

export const Semana: StoryObj = { render: () => <Grid count={7} /> };

export const TresDias: StoryObj = {
  name: "Tres días (móvil)",
  render: () => <Grid count={3} />,
};

export const Dia: StoryObj = { name: "Día", render: () => <Grid count={1} /> };

export const Horario: StoryObj = {
  name: "Horario de lunes a viernes, sin fechas",
  render: () => {
    const lessons: CalendarEvent[] = [
      ev(0, "09:00", "11:00", "Estadística", 1, { subtitle: "A-12", readOnly: true, recurring: true }),
      ev(1, "11:30", "13:30", "Aprendizaje automático", 5, { subtitle: "Lab 2", readOnly: true }),
      ev(2, "09:00", "11:00", "Estadística", 1, { subtitle: "A-12", readOnly: true, status: "cancelled" }),
      ev(3, "16:00", "18:00", "Bases de datos", 6, { subtitle: "A-03", readOnly: true }),
    ];
    return (
      <Frame>
        <TimeGrid label="Horario" days={dayRange(MONDAY, 5)} events={lessons} now={NOW} showDates={false} scrollToHour={8} />
      </Frame>
    );
  },
};

export const Mes: StoryObj = {
  render: () => {
    const { events } = useEvents([
      ...WEEK,
      ...WEEK.filter((e) => !e.allDay).map((e) => ({
        ...e,
        id: `${e.id}-next`,
        start: new Date(new Date(e.start as string).getTime() + 7 * 86_400_000).toISOString(),
        end: new Date(new Date(e.end as string).getTime() + 7 * 86_400_000).toISOString(),
      })),
    ]);
    const [selected, setSelected] = React.useState<string | null>("2026-09-30");
    const [month, setMonth] = React.useState("2026-09-01");
    const [from, setFrom] = React.useState(mondayOf("2026-09-01"));
    const toMonth = (day: string) => {
      setMonth(day);
      setFrom(mondayOf(day));
    };
    return (
      <Frame>
        <MonthGrid
          month={month}
          from={from}
          events={events}
          now={NOW}
          selectedDay={selected}
          onDayClick={setSelected}
          onNavigate={(step) => {
            const date = new Date(`${month}T00:00`);
            date.setMonth(date.getMonth() + step);
            toMonth(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`);
          }}
          onScroll={(weeks) => {
            const next = addDays(from, 7 * weeks);
            setFrom(next);
            setMonth(`${addDays(next, 21).slice(0, 7)}-01`);
          }}
        />
      </Frame>
    );
  },
};

export const MesPequeno: StoryObj = {
  name: "Mes pequeño",
  render: () => {
    const [month, setMonth] = React.useState("2026-09-01");
    const [first, setFirst] = React.useState(MONDAY);
    const marked = new Set(WEEK.map((e) => (typeof e.start === "string" ? e.start.slice(0, 10) : "")));
    return (
      <div className="glass" style={{ width: 280, padding: "var(--space-4)" }}>
        <MiniMonth
          month={month}
          range={dayRange(first, 7)}
          marked={marked}
          weekNumbers
          now={NOW}
          onSelect={(day) => setFirst(mondayOf(day))}
          onMonthChange={(step) => {
            const [y, m] = month.split("-").map(Number) as [number, number];
            const date = new Date(y, m - 1 + step, 1);
            setMonth(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`);
          }}
        />
      </div>
    );
  },
};
