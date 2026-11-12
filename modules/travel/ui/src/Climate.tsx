import { Button, ChoiceChips, GroupLabel, Hint, Skeleton } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type ClimateMonth, type Idea, readClimate } from "./api";
import { goodMonths } from "./weather";
import { MONTHS_SHORT, monthsLabel } from "./words";

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
        } else setProblem(answer.failed ?? "No se ha podido saber el clima.");
      })
      .catch(() => current && setProblem("No se ha podido saber el clima."));
    return () => {
      current = false;
    };
  }, [place]);

  if (!place) return null;
  const good = months ? goodMonths(months) : [];

  return (
    <section className="travel-group">
      <GroupLabel>
        El clima
        {years && <span className="travel-group-detail">de media, {years}</span>}
      </GroupLabel>
      {located.length > 1 && (
        <ChoiceChips
          label="Destino"
          value={chosen}
          onChange={setChosen}
          options={located.map((one) => ({ value: one.place.id, label: one.place.name }))}
        />
      )}
      {problem && <Hint tone="warning">{problem}</Hint>}
      {!months && !problem && <Skeleton label="Cargando el clima" />}
      {months && (
        <div className="surface travel-climate">
          <ol className="travel-climate-months" aria-label={`Clima de ${place.name}`}>
            {months.map((one) => (
              <li
                key={one.month}
                data-chosen={idea.months.includes(one.month) || undefined}
                data-good={good.includes(one.month) || undefined}
              >
                <span className="travel-climate-name">{MONTHS_SHORT[one.month - 1]}</span>
                <span className="travel-climate-max">{Math.round(one.max_c)}°</span>
                <span className="travel-climate-min">{one.min_c !== null ? `${Math.round(one.min_c)}°` : ""}</span>
                <span className="travel-climate-rain">{Math.round(one.rain_days)} 🌧️</span>
              </li>
            ))}
          </ol>
          <p className="travel-climate-note">
            {good.length
              ? `Buenos para ir según el clima (máximas de 15 a 29° y diez días de lluvia o menos): ${monthsLabel(good)}.`
              : "Ningún mes cumple a la vez máximas de 15 a 29° y diez días de lluvia o menos."}
          </p>
          {good.length > 0 && good.join() !== [...idea.months].sort((a, b) => a - b).join() && (
            <Button variant="tinted" size="small" onClick={() => onUseMonths(good)}>
              Usar estos meses
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
