import { Button, ChoiceChips, DateField, SegmentedControl, SelectField, Slider, TextField } from "@openarga/ui";

import type { Genre, Reading } from "./api";
import { t } from "./lang";
import { formats, stars, statuses, todayIso, withStatus } from "./words";

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
        label={t("field.status")}
        options={statuses()}
        value={reading.status}
        onChange={(status) => onChange(withStatus(reading, status, today))}
      />
      {reading.status !== "want" && (
        <div className="library-dates">
          <DateField
            label={t("field.started")}
            max={today}
            value={reading.started_on ?? ""}
            onChange={(value) => set({ started_on: value || null })}
          />
          {reading.status !== "reading" && (
            <DateField
              label={reading.status === "abandoned" ? t("field.abandoned") : t("field.finished")}
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
            <span className="text-field-label">{t("field.rating")}</span>
            <span className="library-rating-value">{reading.rating === null ? t("rating.none") : stars(reading.rating)}</span>
          </div>
          <Slider
            label={t("field.rating")}
            min={0}
            max={5}
            step={0.5}
            value={reading.rating ?? 0}
            valueText={reading.rating === null ? t("rating.none") : t("rating.of_five", { rating: reading.rating })}
            onChange={(rating) => set({ rating })}
          />
          {reading.rating !== null && (
            <Button variant="plain" size="small" onClick={() => set({ rating: null })}>
              {t("rating.remove")}
            </Button>
          )}
        </div>
      )}
      <SegmentedControl label={t("field.format")} options={formats()} value={reading.format} onChange={(format) => set({ format })} />
      <SelectField
        label={t("field.genre")}
        options={genres.map((genre) => ({ value: genre.id, label: genre.name }))}
        value={reading.genre}
        onChange={(genre) => set({ genre })}
      />
      <TextField label={t("field.note")} value={reading.note ?? ""} onChange={(note) => set({ note: note || null })} />
    </div>
  );
}
