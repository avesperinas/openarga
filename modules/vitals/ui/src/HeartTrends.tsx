import { Heading, Hint, SegmentedControl, Skeleton, StatRow, StatTile, TrendChart, useLocale, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type FigureSeries, readFigure } from "./api";
import { figureName } from "./body";
import { heartSummary } from "./heart";
import { decimal, unitName } from "./words";

type Pick = "resting_heart_rate" | "hrv_ms" | "vo2max";

const PICKS: Pick[] = ["resting_heart_rate", "hrv_ms", "vo2max"];

export function HeartTrends() {
  const t = useT();
  const locale = useLocale();
  const options = PICKS.map((value) => ({ value, label: t(`heart.pick.${value}`) }));
  const [picked, setPicked] = useState<Pick>("resting_heart_rate");
  const [found, setFound] = useState<FigureSeries | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    setFound(null);
    setMissing(false);
    readFigure(picked)
      .then(setFound)
      .catch(() => setMissing(true));
  }, [picked]);

  const summary = found ? heartSummary(found, picked === "resting_heart_rate", t, locale) : null;
  const name = found ? figureName(t, found.figure) : "";

  return (
    <section className="surface vitals-card health-figures" aria-label={t("heart.over_time")}>
      <Heading>{t("group.heart")}</Heading>
      <SegmentedControl label={t("heart.which")} options={options} value={picked} onChange={setPicked} />
      {!found && !missing && <Skeleton label={t("heart.loading")} />}
      {(missing || (found && !summary)) && <Hint>{t("heart.no_data")}</Hint>}
      {found && summary && (
        <>
          <StatRow label={name}>
            <StatTile label={t("heart.now")} value={summary.now} />
            <StatTile label={t("heart.month_ago")} value={summary.month} foot={summary.change} tone={summary.tone} />
            <StatTile label={summary.bestLabel} value={summary.best} foot={summary.bestDay} />
          </StatRow>
          <TrendChart
            label={t("heart.last_90", { name })}
            points={summary.points}
            valueName={name}
            averageName={t("heart.mean_7")}
            format={(value) => `${decimal(value, locale, found.figure.digits)} ${unitName(t, found.figure.unit)}`}
          />
        </>
      )}
    </section>
  );
}
