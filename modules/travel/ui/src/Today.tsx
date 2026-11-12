import { mutate } from "@openarga/app";
import { Button, Card, EmptyState, GroupLabel, Hint, Icon, type IconName, Screen, Sheet, useNow } from "@openarga/ui";
import { type CSSProperties, useEffect, useMemo, useState } from "react";

import {
  type Today,
  type TodayEntry,
  type Trip,
  Unauthorised,
  addExpense,
  readForecast,
  readToday,
  readTrip,
  signIn,
} from "./api";
import { ExpenseForm } from "./ExpenseForm";
import { DaySheet, saveDay } from "./Journal";
import { Pending, useLoad } from "./Loads";
import { Queued } from "./offline";
import type { Navigate } from "./App";
import { ScreenHeader } from "./Header";
import { lock } from "./tripApp";
import { TripTabs } from "./TripChrome";
import { clock, onApple, progress } from "./today";
import { dayLine } from "./weather";
import { KINDS, MODES, dateRange, dayLabel, hours } from "./words";

function iconOf(entry: TodayEntry): IconName {
  if (entry.type === "leg") return MODES[entry.kind as keyof typeof MODES]?.icon ?? "train";
  if (entry.type !== "block") return "home";
  return KINDS[entry.kind as keyof typeof KINDS]?.icon ?? "pin";
}

export function TodayScreen({ navigate, tripId }: { navigate: Navigate; tripId?: string }) {
  const inside = tripId ?? lock();
  const now = useNow(60_000);
  const { day, time } = clock(new Date(now));
  const loaded = useLoad<Today>(`today/${day}`, () => readToday(day));
  const found = loaded.data;
  const [problem, setProblem] = useState("");
  const [spending, setSpending] = useState<Trip | null>(null);
  const [spent, setSpent] = useState("");
  const [needsRate, setNeedsRate] = useState(false);
  const [writing, setWriting] = useState(false);

  const state = useMemo(() => (found ? progress(found.entries, time) : null), [found, time]);
  const [weather, setWeather] = useState("");
  useEffect(() => {
    const here = found?.here;
    if (!here) return;
    readForecast(here[0], here[1])
      .then((answer) => {
        const today = answer.weather?.days.find((one) => one.day === day);
        setWeather(today ? `${dayLine(today)} · ${today.sky}` : "");
      })
      .catch(() => setWeather(""));
  }, [found, day]);
  const apple = useMemo(() => onApple(), []);

  if (!found) {
    return (
      <Screen>
        <ScreenHeader title="Hoy" />
        <Pending found={loaded.found} label="Cargando el día" />
      </Screen>
    );
  }

  if (!found.trip) {
    const upcoming = found.next_trip;
    return (
      <Screen>
        <ScreenHeader eyebrow={dayLabel(day)} title="Hoy" />
        <EmptyState
          icon="plane"
          title="Hoy no hay viaje en curso"
          action={
            upcoming
              ? { label: "Ver el siguiente", icon: "arrow-right", onClick: () => navigate({ screen: "trip", id: upcoming.id }) }
              : { label: "Planear un viaje", icon: "plus", onClick: () => navigate({ screen: "edit", id: null }) }
          }
        >
          {upcoming ? `El siguiente es ${upcoming.title}, ${dateRange(upcoming.starts_on, upcoming.ends_on)}.` : "Cuando estés de viaje, aquí sale el día."}
        </EmptyState>
      </Screen>
    );
  }

  const trip = found.trip;
  const done = state?.done ?? [];
  const next = state?.next ?? null;
  const total = found.entries.length;
  const count = done.filter(Boolean).length;
  const coming = next !== null ? found.entries[next] : null;
  const go = (entry: TodayEntry) => (entry.where ? (apple ? entry.where.apple : entry.where.google) : null);

  return (
    <Screen>
      <ScreenHeader
        eyebrow={`${trip.title} · Día ${trip.number} de ${trip.days} · ${dayLabel(day)}`}
        title={trip.day_title ?? `Día ${trip.number} de ${trip.days}`}
      />
      {inside === trip.id && <TripTabs id={trip.id} active="today" navigate={navigate} today />}
      {weather && <p className="travel-today-weather">{weather}</p>}
      {problem && <Hint tone="warning">{problem}</Hint>}
      {total > 0 && (
        <div className="travel-today-progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={count}>
          <span className="travel-today-bar" style={{ "--done": `${(count / total) * 100}%` } as CSSProperties} />
          <span className="travel-today-count">
            {count} de {total}
          </span>
        </div>
      )}
      {coming && (
        <section className="surface travel-today-next">
          <span className="travel-today-label">Lo siguiente</span>
          <span className="travel-today-title">
            <Icon name={iconOf(coming)} />
            {coming.title}
          </span>
          {(coming.starts_at || coming.detail) && (
            <span className="travel-step-detail">
              {[hours(coming.starts_at, coming.ends_at), coming.detail, coming.confirmation].filter(Boolean).join(" · ")}
            </span>
          )}
          {go(coming) && (
            <a className="button travel-today-go" data-variant="primary" data-block href={go(coming)!} target="_blank" rel="noreferrer">
              <Icon name="arrow-right" />
              <span className="button-label">Ir</span>
            </a>
          )}
        </section>
      )}
      {total === 0 && <Hint>Hoy no hay nada en el itinerario. Añádelo en el día a día.</Hint>}
      {total > 0 && (
        <section className="travel-group">
          <GroupLabel>
            El día
            {found.sleeping && <span className="travel-group-detail">Duermes en {found.sleeping}</span>}
          </GroupLabel>
          <ol className="surface travel-day">
            {found.entries.map((entry, index) => (
              <li
                key={`${entry.type}-${entry.id}`}
                className="travel-block travel-today-entry"
                data-done={done[index] || undefined}
                data-next={index === next || undefined}
              >
                <span className="travel-step-mark">
                  <Icon name={done[index] ? "done" : iconOf(entry)} />
                </span>
                <span className="travel-step-text">
                  <span className="travel-step-title">
                    {entry.starts_at && <span className="travel-block-time">{hours(entry.starts_at, entry.ends_at)} </span>}
                    {entry.title}
                  </span>
                  {(entry.detail || entry.confirmation) && (
                    <span className="travel-step-detail">{[entry.detail, entry.confirmation].filter(Boolean).join(" · ")}</span>
                  )}
                </span>
                {go(entry) && !done[index] && (
                  <a className="travel-today-link" href={go(entry)!} target="_blank" rel="noreferrer" aria-label={`Ir a ${entry.title}`}>
                    <Icon name="arrow-right" />
                  </a>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
      <Card
        title="Diario de hoy"
        action={{ icon: "edit", label: found.journal ? "Seguir" : "Escribir", onClick: () => setWriting(true) }}
      >
        {found.journal ? (
          <Hint lines>{found.journal}</Hint>
        ) : (
          <Hint>Lo que pasó hoy, en tus palabras. También sin conexión: se manda al volver la red.</Hint>
        )}
      </Card>
      {writing && (
        <DaySheet
          day={day}
          body={found.journal ?? ""}
          onClose={() => setWriting(false)}
          onSave={async (body) => {
            try {
              void mutate<Today>(`today/${day}`, (now) => (now ? { ...now, journal: body.trim() || null } : now!));
              setSpent(await saveDay({ id: trip.id }, day, body));
              setWriting(false);
            } catch (error) {
              setSpent(error instanceof Error ? error.message : "No se ha podido guardar el diario.");
            }
          }}
        />
      )}
      {spent && <Hint>{spent}</Hint>}
      <div className="travel-actions">
        <Button
          variant="primary"
          icon="wallet"
          onClick={() =>
            readTrip(trip.id)
              .then(setSpending)
              .catch((error: unknown) => {
                if (error instanceof Unauthorised) return signIn();
                setProblem("Sin conexión no se puede abrir el gasto si el viaje no está preparado.");
              })
          }
        >
          Apuntar gasto
        </Button>
        <Button variant="tinted" icon="map" onClick={() => navigate({ screen: "day", id: trip.id, day })}>
          El día en el mapa
        </Button>
        <Button variant="secondary" icon="calendar" onClick={() => navigate({ screen: "days", id: trip.id })}>
          Día a día
        </Button>
      </div>
      {spending && (
        <Sheet title="Apuntar gasto" onClose={() => setSpending(null)}>
          <ExpenseForm
            trip={spending}
            compact
            needsRate={needsRate}
            onSave={async (expense) => {
              try {
                await addExpense(spending.id, expense);
                setSpent(`Apuntado: ${expense.concept}.`);
              } catch (error) {
                if (error instanceof Queued) setSpent(error.message);
                else {
                  setNeedsRate(Boolean(expense.currency));
                  setSpent(error instanceof Error ? error.message : "No se ha podido apuntar.");
                  return false;
                }
              }
              setSpending(null);
              return true;
            }}
          />
        </Sheet>
      )}
    </Screen>
  );
}
