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
import { intl, t } from "./lang";
import { goalPace, ratingRows, shareItems, todayIso, yearDays } from "./words";

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
    setProblem(error instanceof Error ? error.message : t("problem.read"));
  }, []);

  async function saveGoal() {
    const books = Number(goalText);
    if (!found || !Number.isInteger(books) || books < 1) {
      setProblem(t("goal.invalid"));
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
        <ScreenHeader title={t("tab.stats")} />
        <OfflineNotice />
        {stats.error ? (
          <ErrorState title={t("stats.error")} detail={stats.error.message} onRetry={stats.refresh} />
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
      <ScreenHeader title={t("tab.stats")} />
      <OfflineNotice />

      <SelectField
        label={t("edition.year")}
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
          title={t("stats.empty", { year: found.year })}
          action={{ label: t("stats.to_shelf"), icon: "book", onClick: onShelf }}
        >
          {t("stats.empty_body")}
        </EmptyState>
      )}

      {!empty && (
        <Card>
          <HeadlineFigure
            label={t("stats.books")}
            value={number(found.books)}
            unit={found.goal ? t("goal.of", { goal: found.goal }) : undefined}
            change={versus ?? undefined}
          />
          <Figures
            label={t("stats.year")}
            items={[
              { label: t("book.pages"), value: number(found.pages) },
              { label: t("book.pages_per_day"), value: found.pages_per_day.toLocaleString(intl()) },
              { label: t("stats.average"), value: found.average_rating === null ? "–" : `★ ${found.average_rating.toLocaleString(intl())}` },
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
            label={t("stats.goal_books", { books: found.books, goal: found.goal! })}
            detail={goalPace(found) || undefined}
            tone={found.goal_pace !== null && found.books + 0.5 < found.goal_pace ? "warning" : undefined}
          />
        ) : (
          <Hint>{t("goal.none_this_year")}</Hint>
        )}
        {editingGoal ? (
          <div className="library-actions">
            <TextField
              label={t("stats.goal_label")}
              inputMode="numeric"
              value={goalText}
              onChange={setGoalText}
              onSubmit={() => void saveGoal()}
              autoFocus
            />
            <Button variant="tinted" onClick={() => void saveGoal()}>
              {t("action.save")}
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
            {found.goal ? t("goal.change") : t("goal.set")}
          </Button>
        )}
      </section>

      {!empty && (
        <>
          <section className="surface library-panel">
            <Heading>{t("stats.pages_month")}</Heading>
            <SeriesChart
              label={t("stats.pages_month")}
              labels={found.months.map((month) => month.label)}
              series={[{ key: "pages", name: t("edition.pages_label"), values: found.months.map((month) => month.pages) }]}
              format={(value) => t("edition.pages_short", { pages: number(value) })}
              axisFormat={number}
            />
            <Hint>
              {found.months
                .filter((month) => month.books)
                .map((month) => `${month.label}: ${month.books}`)
                .join(" · ") || t("stats.none_finished")}
            </Hint>
          </section>

          <section className="surface library-panel">
            <Heading>{t("stats.pages_day")}</Heading>
            <YearCalendar
              days={yearDays(found.year, found.days, current ? todayIso() : `${found.year}-12-31`)}
              end={current ? todayIso() : `${found.year}-12-31`}
              label={t("stats.pages_day")}
              format={(value) => t("edition.pages_short", { pages: number(value) })}
            />
            <Hint>
              {t("stats.estimate")}
            </Hint>
          </section>
        </>
      )}

      {found.genres.length > 0 && (
        <section className="surface library-panel">
          <Heading>{t("stats.genres")}</Heading>
          <ShareChart label={t("stats.genres")} items={shareItems(found.genres)} format={(value) => t("books.other", { count: value })} />
        </section>
      )}

      {found.authors.length > 0 && (
        <Group title={t("stats.authors")} shares={found.authors} />
      )}

      {Object.keys(found.ratings).length > 0 && (
        <section className="library-group">
          <GroupLabel>{t("stats.ratings")}</GroupLabel>
          <List>
            {ratingRows(found.ratings).map((row) => (
              <ListRow key={row.label} title={row.label} value={row.value} />
            ))}
          </List>
        </section>
      )}

      {found.formats.length > 1 && <Group title={t("stats.formats")} shares={found.formats} />}
      {found.languages.length > 1 && <Group title={t("stats.languages")} shares={found.languages} />}

      {(found.longest || found.fastest) && (
        <section className="library-group">
          <GroupLabel>{t("stats.highlights")}</GroupLabel>
          <List>
            {found.longest && (
              <ListRow
                title={found.longest.title}
                subtitle={t("stats.longest")}
                value={found.longest.pages ? t("edition.pages_short", { pages: found.longest.pages }) : undefined}
                accessory="expand"
                onClick={() => onOpen(found.longest!.id)}
              />
            )}
            {found.fastest && (
              <ListRow
                title={found.fastest.title}
                subtitle={t("stats.fastest")}
                value={found.fastest.days === 1 ? t("stats.one_day") : t("dates.days", { days: found.fastest.days ?? 0 })}
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
            detail={share.pages ? t("edition.pages_short", { pages: number(share.pages) }) : undefined}
            value={share.books === 1 ? t("books.one") : t("books.other", { count: share.books })}
          />
        ))}
      </List>
    </section>
  );
}

export function change(books: number, previous: number, year: number): { text: string; direction: "up" | "down" | "flat" } {
  const diff = books - previous;
  if (diff === 0) return { text: t("change.same", { year }), direction: "flat" };
  return { text: t("change.diff", { diff: `${diff > 0 ? "+" : "−"}${Math.abs(diff)}`, year }), direction: diff > 0 ? "up" : "down" };
}

