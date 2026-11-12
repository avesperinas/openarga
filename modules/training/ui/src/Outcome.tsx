import { BodyMaps, Card, Figures, amountColor, useLocale, useT } from "@openarga/ui";

import type { Outcome, Session, SessionExercise } from "./api";
import { amount, muscleName, plural } from "./labels";

export function OutcomeCard({
  session,
  exercises,
  outcome,
}: {
  session: Session;
  exercises: SessionExercise[];
  outcome: Outcome | null;
}) {
  const t = useT();
  const locale = useLocale();
  const minutes = session.duration_seconds === null ? null : Math.round(session.duration_seconds / 60);
  const sets = exercises.reduce((total, exercise) => total + exercise.sets.filter((set) => set.completed).length, 0);
  const records = new Set(outcome?.records.map((record) => record.variant_id)).size;
  const most = Math.max(0, ...(outcome?.muscles.map((worked) => worked.sets) ?? []));
  const figures = [
    minutes === null ? null : { value: minutes, label: plural(t, "outcome.minutes", minutes) },
    { value: sets, label: plural(t, "outcome.sets", sets) },
    outcome ? { value: records, label: plural(t, "outcome.records", records), lit: records > 0 } : null,
  ].filter((figure) => figure !== null);

  return (
    <Card label={t("outcome.title")}>
      <Figures items={figures} />
      {outcome && outcome.muscles.length > 0 && (
        <BodyMaps
          compact
          label={t("outcome.worked")}
          colors={Object.fromEntries(
            outcome.muscles.map((worked) => [worked.muscle, amountColor(worked.sets / most, "var(--kind)")]),
          )}
          names={Object.fromEntries(
            outcome.muscles.map((worked) => [
              worked.muscle,
              `${muscleName(t, { id: worked.muscle, name: worked.name })}: ${plural(t, "common.sets", worked.sets, { count: amount(worked.sets, locale) })}`,
            ]),
          )}
        />
      )}
    </Card>
  );
}
