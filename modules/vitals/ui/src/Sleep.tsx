import {
  Collapsible,
  Columns,
  EmptyState,
  HealthRing,
  Heading,
  Hint,
  Hypnogram,
  IconButton,
  InfoHeading,
  KeyFigures,
  PartBars,
  List,
  ListRow,
  QUALITY_NAMES,
  QualityMonth,
  Screen,
  SeriesChart,
  Skeleton,
  SleepSchedule,
  StageBreakdown,
  TrendChart,
  YearCalendar,
} from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type NightPage,
  type SleepPatterns,
  type SleepSummary,
  Unauthorised,
  readNight,
  readSleep,
  readSleepPatterns,
  signIn,
} from "./api";
import { ScreenHeader } from "./Header";
import { INFO } from "./info";
import { wakeTiles } from "./rhythm";
import {
  SCORE_INFO,
  againstUsual,
  monthsOf,
  scoreDays,
  scoreParts,
  scoreTrend,
  stageShareList,
  yearAgo,
} from "./nights";
import { STAGES, hours, shortDay, stageSeries, timeOf } from "./sleep";
import { baselineTile, groupLine } from "./workouts";
import { dayLabel } from "./weight";

export function SleepScreen({ onSettings }: { onSettings: () => void }) {
  const [summary, setSummary] = useState<SleepSummary | null>(null);
  const [problem, setProblem] = useState("");
  const [day, setDay] = useState<string | null>(null);
  const [month, setMonth] = useState<string | null>(null);

  useEffect(() => {
    readSleep(yearAgo(new Date()))
      .then((found) => {
        setSummary(found);
        setDay(found.last?.day ?? null);
        setMonth(found.last?.day.slice(0, 7) ?? null);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer el sueño.");
      });
  }, []);

  const nights = summary?.nights ?? [];
  const months = useMemo(() => monthsOf(nights), [nights]);
  const recent = nights.slice(-30);
  const at = month ? months.indexOf(month) : -1;

  const open = (picked: string) => {
    setDay(picked);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <Screen wide>
      <ScreenHeader title="Sueño" />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {summary === null && !problem && <Skeleton label="Cargando el sueño" />}

      {summary && summary.last === null && (
        <EmptyState
          title="Todavía no ha llegado ninguna noche"
          action={{ label: "Ir a Ajustes", onClick: onSettings }}
        >
          El sueño llega de la pulsera por Google Health. En Ajustes está cómo
          conectarla.
        </EmptyState>
      )}

      {day && <NightCard day={day} onDay={setDay} />}

      <Columns count={2} stack>
        {month && nights.length > 0 && (
          <section className="surface vitals-card" aria-label="El mes">
            <InfoHeading info={INFO.calendar}>
              Calidad de cada noche
            </InfoHeading>
            <QualityMonth
              label="La nota de cada noche del mes"
              month={month}
              days={scoreDays(nights)}
              selected={day}
              onSelect={open}
              onPrevious={
                at > 0 ? () => setMonth(months[at - 1] ?? month) : undefined
              }
              onNext={
                at >= 0 && at < months.length - 1
                  ? () => setMonth(months[at + 1] ?? month)
                  : undefined
              }
            />
          </section>
        )}

        {recent.length > 1 && summary && (
          <section
            className="surface vitals-card health-figures"
            aria-label="El horario"
          >
            <InfoHeading info={INFO.schedule}>Horario de sueño</InfoHeading>
            <SleepSchedule
              label="De qué hora a qué hora dormiste las últimas noches"
              nights={recent
                .slice(-14)
                .map((one) => ({
                  day: one.day,
                  start: one.start,
                  end: one.end,
                  quality: one.score?.quality ?? null,
                }))}
              formatDay={shortDay}
            />
            <Regularity summary={summary} />
          </section>
        )}
      </Columns>
      <Columns count={2} stack>
        {nights.length > 2 && (
          <section className="surface vitals-card" aria-label="Las tendencias">
            <InfoHeading info={INFO.trend}>Tendencia</InfoHeading>
            <TrendChart
              label="La nota de cada noche y su media de 7"
              points={scoreTrend(nights.slice(-90))}
              band={{ low: 80, high: 100 }}
              bandName="Buena o mejor"
              valueName="Nota"
              averageName="Media de 7 noches"
              format={(value) => String(Math.round(value))}
            />
            {recent.some((one) => one.stages) && (
              <Collapsible
                title="Fases de cada noche"
                subtitle="Horas de cada fase en las últimas noches"
              >
                <SeriesChart
                  label="Horas de cada fase en las últimas noches"
                  kind="stacked"
                  palette="stages"
                  labels={recent.map((one) => shortDay(one.day))}
                  series={stageSeries(recent)}
                  order={STAGES.map((one) => one.id)}
                  format={(value) => hours(value * 60)}
                  axisFormat={(value) =>
                    `${value.toLocaleString("es-ES", { maximumFractionDigits: 1 })} h`
                  }
                />
              </Collapsible>
            )}
          </section>
        )}

        {nights.length > 7 && (
          <section className="surface vitals-card" aria-label="El año">
            <InfoHeading info={INFO.year}>El año</InfoHeading>
            <YearCalendar
              label="La nota de cada noche del año"
              days={scoreDays(nights)}
              goal={80}
              format={(value) => `nota ${value}`}
            />
            <Hint>En verde, las noches buenas o mejores (80 o más).</Hint>
          </section>
        )}
      </Columns>

      {summary?.last && <PatternsCard />}
      <Hint>Vitals enseña cifras; no diagnostica ni aconseja.</Hint>
      <AppVersion />
    </Screen>
  );
}

function NightCard({
  day,
  onDay,
}: {
  day: string;
  onDay: (day: string) => void;
}) {
  const [page, setPage] = useState<NightPage | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    setProblem("");
    readNight(day)
      .then(setPage)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer esa noche.");
      });
  }, [day]);

  if (problem) return <Hint tone="warning">{problem}</Hint>;
  if (!page || page.night.day !== day)
    return <Skeleton label="Cargando la noche" />;
  const { night, mean_30: usual } = page;
  const score = night.score;
  const woke = wakeTiles(night);

  return (
    <section
      className="surface vitals-card health-figures"
      aria-label={`La noche del ${dayLabel(night.day)}`}
    >
      <div className="vitals-night-head">
        <IconButton
          icon="chevron-left"
          label="Noche anterior"
          variant="plain"
          disabled={!page.previous}
          onClick={() => page.previous && onDay(page.previous)}
        />
        <Heading>{`La noche del ${dayLabel(night.day)}`}</Heading>
        <IconButton
          icon="chevron-right"
          label="Noche siguiente"
          variant="plain"
          disabled={!page.next}
          onClick={() => page.next && onDay(page.next)}
        />
      </div>

      <div className="vitals-night-top">
        {score && (
          <HealthRing
            value={score.value}
            target={100}
            display={String(score.value)}
            caption={QUALITY_NAMES[score.quality]}
            quality={score.quality}
            label="Nota del sueño"
            size="l"
            info={SCORE_INFO}
          />
        )}
        <KeyFigures
          label="La noche"
          items={[
            {
              label: "Dormido",
              value: hours(night.minutes_asleep),
              foot: againstUsual(night.minutes_asleep, usual.asleep),
              info: INFO.sleepMinutes,
            },
            {
              label: "En la cama",
              value: `${timeOf(night.start)} – ${timeOf(night.end)}`,
              foot: night.minutes_in_bed
                ? hours(night.minutes_in_bed)
                : undefined,
              info: INFO.inBed,
            },
            ...(night.minutes_to_fall_asleep != null
              ? [
                  {
                    label: "Tardaste en dormirte",
                    value: hours(night.minutes_to_fall_asleep),
                    info: INFO.fellAsleep,
                  },
                ]
              : []),
            ...(night.nap_minutes > 0
              ? [
                  {
                    label: "Siestas",
                    value: hours(night.nap_minutes),
                    info: INFO.naps,
                  },
                ]
              : []),
          ]}
        />
      </div>

      {score && (
        <PartBars label="La nota, por partes" parts={scoreParts(score)} />
      )}

      {night.segments.length > 0 && (
        <>
          <InfoHeading info={INFO.hypnogram}>Las fases de la noche</InfoHeading>
          <Hypnogram
            segments={night.segments}
            start={night.start}
            end={night.end}
            pulse={page.heart}
            label="Las fases de la noche, con el vitals encima"
          />
        </>
      )}
      {(night.stages || page.figures.length > 0 || woke.length > 0) && (
        <Collapsible
          title="Más de la noche"
          subtitle={moreLine(page, woke.length)}
        >
          {night.stages && (
            <>
              <InfoHeading info={INFO.stages}>Cuánto de cada fase</InfoHeading>
              <StageBreakdown stages={stageShareList(night, usual)} />
            </>
          )}
          {page.figures.length > 0 && (
            <>
              <InfoHeading info={INFO.normal}>
                La noche contra tu normal
              </InfoHeading>
              <KeyFigures
                label="La noche contra tu normal"
                items={page.figures.map((one) => {
                  const tile = baselineTile(one);
                  return {
                    label: one.name,
                    value: tile.value,
                    foot: tile.foot,
                    tone: tile.tone === "warning" ? "warning" : undefined,
                    info: NIGHT_INFO[one.id],
                  };
                })}
              />
            </>
          )}
          {woke.length > 0 && (
            <KeyFigures
              label="Los despertares"
              items={woke.map((one) => ({ ...one, info: INFO.awakenings }))}
            />
          )}
        </Collapsible>
      )}
    </section>
  );
}

function Regularity({ summary }: { summary: SleepSummary }) {
  const [found, setFound] = useState<SleepPatterns | null>(null);
  useEffect(() => {
    readSleepPatterns()
      .then(setFound)
      .catch(() => setFound(null));
  }, []);
  const mean = summary.mean_30;
  return (
    <KeyFigures
      label="Regularidad"
      items={[
        {
          label: "Te duermes, de media",
          value: clockText(mean.fell_asleep_at),
          foot:
            found?.fell_asleep_spread != null
              ? `± ${found.fell_asleep_spread} min`
              : undefined,
          info: INFO.regularity,
        },
        {
          label: "Te despiertas, de media",
          value: clockText(mean.woke_at),
          foot:
            found?.woke_spread != null
              ? `± ${found.woke_spread} min`
              : undefined,
          info: INFO.regularity,
        },
        {
          label: "Dormido, media de 30",
          value: hours(mean.asleep),
          foot: `${mean.nights} noches`,
        },
      ]}
    />
  );
}

function moreLine(page: NightPage, awakenings: number): string {
  const hrv = page.figures.find((one) => one.id === "hrv_ms");
  return [
    page.night.stages ? "Fases" : null,
    hrv && hrv.value !== null ? `VFC ${Math.round(hrv.value)} ms` : null,
    awakenings > 0 && page.night.awakenings
      ? `${page.night.awakenings} ${page.night.awakenings === 1 ? "despertar" : "despertares"}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

const NIGHT_INFO: Record<string, string> = {
  hrv_ms: INFO.hrv,
  respiratory_rate: INFO.respiration,
  spo2_pct: INFO.spo2,
  skin_temp_delta_c: INFO.skinTemp,
};

function clockText(minutes: number | null): string {
  if (minutes === null) return "—";
  const day = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(day / 60)).padStart(2, "0")}:${String(day % 60).padStart(2, "0")}`;
}

function PatternsCard() {
  const [found, setFound] = useState<SleepPatterns | null>(null);
  useEffect(() => {
    readSleepPatterns()
      .then(setFound)
      .catch(() => setFound(null));
  }, []);
  if (!found || found.comparisons.length === 0) return null;
  return (
    <section
      className="surface vitals-card"
      aria-label="El sueño y el día de antes"
    >
      <InfoHeading info={INFO.afterTraining}>
        El sueño y el día de antes
      </InfoHeading>
      <List>
        {found.comparisons.map((one) => (
          <ListRow
            key={one.label}
            title={one.label}
            subtitle={`${groupLine(one.after)}. El resto: ${groupLine(one.rest)}.`}
          />
        ))}
      </List>
      <Hint>Medias de los últimos 90 días. No dicen por qué.</Hint>
    </section>
  );
}
