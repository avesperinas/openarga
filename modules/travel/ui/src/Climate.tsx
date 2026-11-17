import { Button, ChoiceChips, GroupLabel, Hint, Skeleton } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type ClimateMonth, type Idea, readClimate } from "./api";
import { goodMonths } from "./weather";
import { monthShort, monthsLabel } from "./words";
import { t } from "./lang";

export function ClimateCard({ idea, onUseMonths }: { idea: Idea; onUseMonths: (months: number[]) => void }) {
  const located = idea.places.filter((one) => one.place.lat !== null && one.place.lon !== null);
  const [chosen, setChosen] = useState(located[0]?.place.id ?? "");
  const [months, setMonths] = useState<ClimateMonth[] | null>(null);
  const [years, setYears] = useState("");
  const [problem, setProblem] = useState("");
  const place = located.find((one) => one.place.id === chosen)?.place;

  useEffect(() => {
    if (!place || place.lat === null || place.lon === null) return;
    let current = true;
    setMonths(null);
    setProblem("");
    readClimate(place.lat, place.lon)
      .then((answer) => {
        if (!current) return;
        if (answer.weather) {
          setMonths(answer.weather.months);
          setYears(answer.weather.years);
        } else setProblem(answer.failed ?? t("climate.error"));
      })
      .catch(() => current && setProblem(t("climate.error")));
    return () => {
      current = false;
    };
  }, [place]);

  if (!place) return null;
  const good = months ? goodMonths(months) : [];

  return (
    <section className="travel-group">
      <GroupLabel>
        {t("climate.title")}
        {years && <span className="travel-group-detail">{t("climate.average", { years })}</span>}
      </GroupLabel>
      {located.length > 1 && (
        <ChoiceChips
          label={t("idea.place")}
          value={chosen}
          onChange={setChosen}
          options={located.map((one) => ({ value: one.place.id, label: one.place.name }))}
        />
      )}
      {problem && <Hint tone="warning">{problem}</Hint>}
      {!months && !problem && <Skeleton label={t("climate.loading")} />}
      {months && (
        <div className="surface travel-climate">
          <ol className="travel-climate-months" aria-label={t("climate.of", { name: place.name })}>
            {months.map((one) => (
              <li
                key={one.month}
                data-chosen={idea.months.includes(one.month) || undefined}
                data-good={good.includes(one.month) || undefined}
              >
                <span className="travel-climate-name">{monthShort(one.month)}</span>
                <span className="travel-climate-max">{Math.round(one.max_c)}°</span>
                <span className="travel-climate-min">{one.min_c !== null ? `${Math.round(one.min_c)}°` : ""}</span>
                <span className="travel-climate-rain">{Math.round(one.rain_days)} 🌧️</span>
              </li>
            ))}
          </ol>
          <p className="travel-climate-note">
            {good.length
              ? t("climate.good", { months: monthsLabel(good) })
              : t("climate.none_good")}
          </p>
          {good.length > 0 && good.join() !== [...idea.months].sort((a, b) => a - b).join() && (
            <Button variant="tinted" size="small" onClick={() => onUseMonths(good)}>
              {t("climate.use")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
