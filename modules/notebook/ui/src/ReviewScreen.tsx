import { Button, EmptyState, OfflineNotice } from "@openarga/ui";

import { type NoteSummary, readReview } from "./api";
import { Pending, useLoad } from "./Loads";

function late(due: string, now = new Date()): string {
  const days = Math.round((Date.parse(now.toISOString().slice(0, 10)) - Date.parse(due)) / 86_400_000);
  return days <= 0 ? "hoy" : days === 1 ? "ayer" : `hace ${days} días`;
}

export function ReviewScreen({ onOpen, onSettings }: { onOpen: (note: NoteSummary) => void; onSettings: () => void }) {
  const { data: review, found } = useLoad("review", readReview, { persist: true });

  if (!review) return <Pending found={found} />;
  if (!review.chosen) {
    return (
      <EmptyState icon="calendar" title="¿Qué propiedad dice cuándo repasar?" action={{ label: "Elegirla", onClick: onSettings }}>
        Si tus notas llevan una fecha de repaso en sus propiedades, como naechste_wiederholung, elígela y aquí saldrá lo
        que toca cada día.
      </EmptyState>
    );
  }
  if (review.notes.length === 0) {
    return (
      <EmptyState icon="done" title="Nada que repasar hoy" action={{ label: "Cambiar la propiedad", onClick: onSettings }}>
        Las notas con la fecha de repaso de hoy o de antes salen aquí.
      </EmptyState>
    );
  }
  return (
    <div className="mn-search">
      <OfflineNotice />
      <ul className="mn-hits">
        {review.notes.map((note) => (
          <li key={note.id}>
            <button type="button" className="mn-hit" onClick={() => onOpen(note)}>
              <span className="mn-hit-title">{note.title}</span>
              <span className="mn-hit-path">
                {late(note.due)}
                {note.folder ? ` · ${note.folder}` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <Button variant="plain" onClick={onSettings}>
        Cambiar la propiedad del repaso
      </Button>
    </div>
  );
}
