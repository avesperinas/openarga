import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Figures,
  GroupLabel,
  Heading,
  HeadlineFigure,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  RingFigure,
  Screen,
  SeriesChart,
  plain,
  SelectField,
  ShareChart,
  Skeleton,
  TextField,
  YearCalendar,
} from "@openarga/ui";
import { mutate, useResource } from "@openarga/app";
import { useCallback, useState } from "react";

import { type Share, Unauthorised, type YearStats, readStats, setGoal, signIn } from "./api";
import { ScreenHeader } from "./Header";
import { goalFoot, ratingRows, shareItems, todayIso, yearDays } from "./words";

const number = (value: number) => plain(Math.round(value));

export function StatsScreen({ onOpen, onShelf }: { onOpen: (id: string) => void; onShelf: () => void }) {
  const thisYear = Number(todayIso().slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const key = `stats:${year}`;
  const stats = useResource(key, () => readStats(year === thisYear ? undefined : year));
  const found = stats.data ?? null;
  const before = useResource(`stats:${year - 1}`, () => readStats(year - 1));
  const versus = found && before.data && before.data.books > 0 ? change(found.books, before.data.books, year - 1) : null;
  const [problem, setProblem] = useState("");
  const [goalText, setGoalText] = useState("");
  const [editingGoal, setEditingGoal] = useState(false);

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : "No se pudo leer.");
  }, []);

  async function saveGoal() {
    const books = Number(goalText);
    if (!found || !Number.isInteger(books) || books < 1) {
      setProblem("El objetivo es un número de libros, de uno para arriba.");
      return;
    }
    try {
      await mutate<YearStats>(key, { ...found, goal: books }, { request: () => setGoal(found.year, books) });
      setEditingGoal(false);
      setProblem("");
    } catch (error) {
      fail(error);
    }
  }

  if (!found) {
    return (
      <Screen>
        <ScreenHeader title="Estadísticas" />
        <OfflineNotice />
        {stats.error ? (
          <ErrorState title="No se han podido leer las cifras" detail={stats.error.message} onRetry={stats.refresh} />
        ) : (
          <Skeleton rows={6} />
        )}
      </Screen>
    );
  }

  const current = found.year === Number(todayIso().slice(0, 4));
  const empty = found.books === 0 && found.pages === 0;

  return (
    <Screen>
      <ScreenHeader title="Estadísticas" />
      <OfflineNotice />

      <SelectField
        label="Año"
        hideLabel
        options={found.years.map((one) => ({ value: String(one), label: String(one) }))}
        value={String(found.year)}
        onChange={(value) => setYear(Number(value))}
      />

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}

      {empty && (
        <EmptyState
          icon="chart"
          hue={5}
          title={`Nada leído en ${found.year}`}
          action={{ label: "Ir a la estantería", icon: "book", onClick: onShelf }}
        >
          Las cifras salen de las fechas de cada libro: apunta cuándo empezaste y terminaste los de este año.
        </EmptyState>
      )}

      {!empty && (
        <Card>
          <HeadlineFigure
            label="Libros"
            value={number(found.books)}
            unit={found.goal ? `de ${found.goal}` : undefined}
            change={versus ?? undefined}
          />
          <Figures
            label="El año"
            items={[
              { label: "páginas", value: number(found.pages) },
              { label: "páginas al día", value: found.pages_per_day.toLocaleString("es-ES") },
              { label: "de media", value: found.average_rating === null ? "–" : `★ ${found.average_rating.toLocaleString("es-ES")}` },
            ]}
          />
        </Card>
      )}
      <section className="surface library-panel">
        <Heading>Objetivo {found.year}</Heading>
        {found.goal ? (
          <RingFigure
            size="medium"
            share={found.books / found.goal}
            value={found.books}
            label={`${found.books} de ${found.goal} libros`}
            detail={goalFoot(found).replace(`de ${found.goal} · `, "").replace(`de ${found.goal}`, "") || undefined}
            tone={found.goal_pace !== null && found.books + 0.5 < found.goal_pace ? "warning" : undefined}
          />
        ) : (
          <Hint>Sin objetivo para este año.</Hint>
        )}
        {editingGoal ? (
          <div className="library-actions">
            <TextField
              label="Libros en el año"
              inputMode="numeric"
              value={goalText}
              onChange={setGoalText}
              onSubmit={() => void saveGoal()}
              autoFocus
            />
            <Button variant="tinted" onClick={() => void saveGoal()}>
              Guardar
            </Button>
          </div>
        ) : (
          <Button
            variant="plain"
            onClick={() => {
              setGoalText(found.goal?.toString() ?? "");
              setEditingGoal(true);
            }}
          >
            {found.goal ? "Cambiar objetivo" : "Poner objetivo"}
          </Button>
        )}
      </section>

      {!empty && (
        <>
          <section className="surface library-panel">
            <Heading>Páginas por mes</Heading>
            <SeriesChart
              label="Páginas por mes"
              labels={found.months.map((month) => month.label)}
              series={[{ key: "pages", name: "Páginas", values: found.months.map((month) => month.pages) }]}
              format={(value) => `${number(value)} págs.`}
              axisFormat={number}
            />
            <Hint>
              {found.months
                .filter((month) => month.books)
                .map((month) => `${month.label}: ${month.books}`)
                .join(" · ") || "Ningún libro terminado todavía."}
            </Hint>
          </section>

          <section className="surface library-panel">
            <Heading>Páginas cada día</Heading>
            <YearCalendar
              days={yearDays(found.year, found.days, current ? todayIso() : `${found.year}-12-31`)}
              end={current ? todayIso() : `${found.year}-12-31`}
              label="Páginas cada día"
              format={(value) => `${number(value)} págs.`}
            />
            <Hint>
              Una estimación: las páginas de cada libro se reparten a partes iguales entre su inicio y su fin.
            </Hint>
          </section>
        </>
      )}

      {found.genres.length > 0 && (
        <section className="surface library-panel">
          <Heading>Temáticas</Heading>
          <ShareChart label="Temáticas" items={shareItems(found.genres)} format={(value) => `${value} libros`} />
        </section>
      )}

      {found.authors.length > 0 && (
        <Group title="Autores más leídos" shares={found.authors} />
      )}

      {Object.keys(found.ratings).length > 0 && (
        <section className="library-group">
          <GroupLabel>Valoraciones</GroupLabel>
          <List>
            {ratingRows(found.ratings).map((row) => (
              <ListRow key={row.label} title={row.label} value={row.value} />
            ))}
          </List>
        </section>
      )}

      {found.formats.length > 1 && <Group title="Formatos" shares={found.formats} />}
      {found.languages.length > 1 && <Group title="Idiomas" shares={found.languages} />}

      {(found.longest || found.fastest) && (
        <section className="library-group">
          <GroupLabel>Destacados</GroupLabel>
          <List>
            {found.longest && (
              <ListRow
                title={found.longest.title}
                subtitle="El más largo"
                value={found.longest.pages ? `${found.longest.pages} págs.` : undefined}
                accessory="expand"
                onClick={() => onOpen(found.longest!.id)}
              />
            )}
            {found.fastest && (
              <ListRow
                title={found.fastest.title}
                subtitle="El más rápido"
                value={found.fastest.days === 1 ? "1 día" : `${found.fastest.days} días`}
                accessory="expand"
                onClick={() => onOpen(found.fastest!.id)}
              />
            )}
          </List>
        </section>
      )}
    </Screen>
  );
}

function Group({ title, shares }: { title: string; shares: Share[] }) {
  return (
    <section className="library-group">
      <GroupLabel>{title}</GroupLabel>
      <List>
        {shares.map((share) => (
          <ListRow
            key={share.id}
            title={share.name}
            detail={share.pages ? `${number(share.pages)} págs.` : undefined}
            value={share.books === 1 ? "1 libro" : `${share.books} libros`}
          />
        ))}
      </List>
    </section>
  );
}

export function change(books: number, previous: number, year: number): { text: string; direction: "up" | "down" | "flat" } {
  const diff = books - previous;
  if (diff === 0) return { text: `igual que en ${year}`, direction: "flat" };
  return { text: `${diff > 0 ? "+" : "−"}${Math.abs(diff)} que en ${year}`, direction: diff > 0 ? "up" : "down" };
}

