import { Button, Heading, Hint, List, ListRow, SeriesChart, Skeleton, useLocale, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Ecg, type EcgTrace, type Irn, Unauthorised, readEcg, readEcgs, readIrns, signIn } from "./api";
import { ecgSeries, irnFoot } from "./rhythm";
import { timeOf } from "./sleep";
import { dayLabel } from "./weight";
import { decimal } from "./words";

export function RhythmCard({ alertsEnabled }: { alertsEnabled: boolean | null }) {
  const t = useT();
  const locale = useLocale();
  const [ecgs, setEcgs] = useState<Ecg[] | null>(null);
  const [alerts, setAlerts] = useState<Irn[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [trace, setTrace] = useState<EcgTrace | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    Promise.all([readEcgs(), readIrns()])
      .then(([found, raised]) => {
        setEcgs(found);
        setAlerts(raised);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("rhythm.read_failed"));
      });
  }, [t]);

  useEffect(() => {
    if (!chosen) return;
    setTrace(null);
    readEcg(chosen)
      .then(setTrace)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("rhythm.ecg_failed"));
      });
  }, [chosen, t]);

  if (ecgs !== null && alerts !== null && ecgs.length === 0 && alerts.length === 0 && alertsEnabled === null) return null;
  const drawn = trace ? ecgSeries(trace, t, locale) : null;
  const result = (one: Ecg) => {
    const key = `ecg.result.${one.result ?? ""}`;
    const found = t(key);
    return found === key ? (one.result_text ?? t("ecg.no_result")) : found;
  };

  return (
    <section className="surface vitals-card" aria-label={t("rhythm.heading")}>
      <Heading>{t("rhythm.heading")}</Heading>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {ecgs === null && !problem && <Skeleton label={t("rhythm.loading")} />}
      {ecgs && ecgs.length > 0 && (
        <List>
          {ecgs.map((one) => (
            <ListRow
              key={one.id}
              title={t("ecg.of_day", { day: dayLabel(one.start.slice(0, 10), locale) })}
              subtitle={`${timeOf(one.start)} · ${result(one)}`}
              value={one.heart_rate_avg != null ? t("common.bpm", { value: Math.round(one.heart_rate_avg) }) : "—"}
              accessory={one.id === chosen ? "done" : "chevron-right"}
              aria-pressed={one.id === chosen}
              onClick={() => setChosen(one.id)}
            />
          ))}
        </List>
      )}
      {chosen && trace === null && !problem && <Skeleton label={t("ecg.loading_trace")} />}
      {trace && drawn && (
        <>
          <SeriesChart
            label={t("ecg.trace", { day: dayLabel(trace.start.slice(0, 10), locale) })}
            kind="lines"
            labels={drawn.labels}
            series={drawn.series}
            format={(value) => `${decimal(value, locale, 2)} mV`}
          />
          <div className="vitals-actions">
            <Button variant="plain" onClick={() => setChosen(null)}>
              {t("ecg.close_trace")}
            </Button>
          </div>
        </>
      )}
      {alerts && alerts.length > 0 && (
        <List>
          {alerts.map((one) => (
            <ListRow
              key={one.id}
              title={t("irn.title")}
              subtitle={[`${dayLabel(one.start.slice(0, 10), locale)}, ${timeOf(one.start)} – ${timeOf(one.end)}`, irnFoot(one, t)]
                .filter(Boolean)
                .join(" · ")}
            />
          ))}
        </List>
      )}
      {alertsEnabled === false && (
        <Hint>{t("irn.disabled")}</Hint>
      )}
      <Hint>{t("rhythm.as_is")}</Hint>
    </section>
  );
}
