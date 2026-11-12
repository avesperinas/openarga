import { Button, ChoiceChips, DateField, SegmentedControl, SelectField, Slider, TextField } from "@openarga/ui";

import type { Genre, Reading } from "./api";
import { FORMATS, STATUSES, stars, todayIso, withStatus } from "./words";

export function ReadingFields({
  reading,
  genres,
  onChange,
}: {
  reading: Reading;
  genres: Genre[];
  onChange: (reading: Reading) => void;
}) {
  const today = todayIso();
  const set = (changes: Partial<Reading>) => onChange({ ...reading, ...changes });

  return (
    <div className="library-fields">
      <ChoiceChips
        label="Estado"
        options={STATUSES}
        value={reading.status}
        onChange={(status) => onChange(withStatus(reading, status, today))}
      />
      {reading.status !== "want" && (
        <div className="library-dates">
          <DateField
            label="Empezado"
            max={today}
            value={reading.started_on ?? ""}
            onChange={(value) => set({ started_on: value || null })}
          />
          {reading.status !== "reading" && (
            <DateField
              label={reading.status === "abandoned" ? "Dejado" : "Terminado"}
              max={today}
              value={reading.finished_on ?? ""}
              onChange={(value) => set({ finished_on: value || null })}
            />
          )}
        </div>
      )}
      {reading.status !== "want" && (
        <div className="library-rating">
          <div className="library-rating-head" aria-hidden="true">
            <span className="text-field-label">Valoración</span>
            <span className="library-rating-value">{reading.rating === null ? "Sin valorar" : stars(reading.rating)}</span>
          </div>
          <Slider
            label="Valoración"
            min={0}
            max={5}
            step={0.5}
            value={reading.rating ?? 0}
            valueText={reading.rating === null ? "sin valorar" : `${reading.rating} de 5`}
            onChange={(rating) => set({ rating })}
          />
          {reading.rating !== null && (
            <Button variant="plain" size="small" onClick={() => set({ rating: null })}>
              Quitar valoración
            </Button>
          )}
        </div>
      )}
      <SegmentedControl label="Formato" options={FORMATS} value={reading.format} onChange={(format) => set({ format })} />
      <SelectField
        label="Temática"
        options={genres.map((genre) => ({ value: genre.id, label: genre.name }))}
        value={reading.genre}
        onChange={(genre) => set({ genre })}
      />
      <TextField label="Nota" value={reading.note ?? ""} onChange={(note) => set({ note: note || null })} />
    </div>
  );
}
