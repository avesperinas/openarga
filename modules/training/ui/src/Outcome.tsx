import { BodyMaps, Card, Figures, amountColor } from "@openarga/ui";

import type { Outcome, Session, SessionExercise } from "./api";

function count(value: number, one: string, many: string): string {
  return value === 1 ? one : many;
}

export function OutcomeCard({
  session,
  exercises,
  outcome,
}: {
  session: Session;
  exercises: SessionExercise[];
  outcome: Outcome | null;
}) {
  const minutes = session.duration_seconds === null ? null : Math.round(session.duration_seconds / 60);
  const sets = exercises.reduce((total, exercise) => total + exercise.sets.filter((set) => set.completed).length, 0);
  const records = new Set(outcome?.records.map((record) => record.variant_id)).size;
  const most = Math.max(0, ...(outcome?.muscles.map((worked) => worked.sets) ?? []));
  const figures = [
    minutes === null ? null : { value: minutes, label: count(minutes, "minuto", "minutos") },
    { value: sets, label: count(sets, "serie", "series") },
    outcome ? { value: records, label: count(records, "récord", "récords"), lit: records > 0 } : null,
  ].filter((figure) => figure !== null);

  return (
    <Card label="Cómo fue">
      <Figures items={figures} />
      {outcome && outcome.muscles.length > 0 && (
        <BodyMaps
          compact
          label="Lo trabajado"
          colors={Object.fromEntries(
            outcome.muscles.map((worked) => [worked.muscle, amountColor(worked.sets / most, "var(--kind)")]),
          )}
          names={Object.fromEntries(
            outcome.muscles.map((worked) => [
              worked.muscle,
              `${worked.name}: ${String(worked.sets).replace(".", ",")} ${count(worked.sets, "serie", "series")}`,
            ]),
          )}
        />
      )}
    </Card>
  );
}
