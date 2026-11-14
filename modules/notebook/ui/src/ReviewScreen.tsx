import { Button, EmptyState, OfflineNotice } from "@openarga/ui";

import { type NoteSummary, readReview } from "./api";
import { Pending, useLoad } from "./Loads";
import { t } from "./lang";

function late(due: string, now = new Date()): string {
  const days = Math.round((Date.parse(now.toISOString().slice(0, 10)) - Date.parse(due)) / 86_400_000);
  return days <= 0 ? t("review.today") : days === 1 ? t("review.yesterday") : t("review.days_ago", { days });
}

export function ReviewScreen({ onOpen, onSettings }: { onOpen: (note: NoteSummary) => void; onSettings: () => void }) {
  const { data: review, found } = useLoad("review", readReview, { persist: true });

  if (!review) return <Pending found={found} />;
  if (!review.chosen) {
    return (
      <EmptyState icon="calendar" title={t("review.unset")} action={{ label: t("review.choose"), onClick: onSettings }}>
        {t("review.unset_detail")}
      </EmptyState>
    );
  }
  if (review.notes.length === 0) {
    return (
      <EmptyState icon="done" title={t("review.empty")} action={{ label: t("review.change"), onClick: onSettings }}>
        {t("review.empty_detail")}
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
        {t("review.change_long")}
      </Button>
    </div>
  );
}
