import { mutate, useResource } from "@openarga/app";
import { EmptyState, ErrorState, Hint, List, ListRow, Sheet, Skeleton } from "@openarga/ui";
import { useState } from "react";

import { type JournalEntry, Queued, type Trip, readJournal, writeJournal } from "./api";
import { addDays, dayLabel, todayIso } from "./words";
import { t } from "./lang";

export const journalKey = (tripId: string) => `journal/${tripId}`;

export function daysSoFar(trip: Pick<Trip, "starts_on" | "ends_on">, today = todayIso()): string[] {
  const last = trip.ends_on < today ? trip.ends_on : today;
  const days: string[] = [];
  for (let day = trip.starts_on; day <= last; day = addDays(day, 1)) days.unshift(day);
  return days;
}

export function withDay(found: JournalEntry[], tripId: string, day: string, body: string): JournalEntry[] {
  const rest = found.filter((one) => one.day !== day);
  const text = body.trim();
  if (!text) return rest;
  const before = found.find((one) => one.day === day);
  const entry = { id: before?.id ?? "", trip_id: tripId, day, body: text, updated_at: new Date().toISOString() };
  return [...rest, entry].sort((a, b) => a.day.localeCompare(b.day));
}

export async function saveDay(trip: Pick<Trip, "id">, day: string, body: string): Promise<string> {
  try {
    await mutate<JournalEntry[]>(journalKey(trip.id), (now) => withDay(now ?? [], trip.id, day, body), {
      request: () => writeJournal(trip.id, day, body),
    });
    return "";
  } catch (error) {
    if (error instanceof Queued) return error.message;
    throw error;
  }
}

export function DaySheet({
  day,
  body,
  onClose,
  onSave,
}: {
  day: string;
  body: string;
  onClose: () => void;
  onSave: (body: string) => Promise<void>;
}) {
  const [text, setText] = useState(body);
  const [busy, setBusy] = useState(false);
  return (
    <Sheet
      title={dayLabel(day)}
      onClose={onClose}
      action={{
        label: busy ? t("journal.saving") : t("action.save"),
        disabled: busy,
        onClick: () => {
          setBusy(true);
          void onSave(text).finally(() => setBusy(false));
        },
      }}
    >
      <label className="text-field">
        <span className="text-field-label">{t("journal.what")}</span>
        <textarea
          className="text-field-input"
          value={text}
          rows={8}
          maxLength={20000}
          placeholder={t("journal.example")}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <Hint>{t("journal.private")}</Hint>
    </Sheet>
  );
}

export function JournalSection({ trip }: { trip: Trip }) {
  const found = useResource(journalKey(trip.id), () => readJournal(trip.id), { persist: true });
  const [open, setOpen] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const days = daysSoFar(trip);

  if (!found.data) {
    if (found.error) {
      return <ErrorState title={t("journal.error")} detail={found.error.message} onRetry={found.refresh} />;
    }
    return <Skeleton label={t("journal.loading")} />;
  }
  if (days.length === 0) {
    return (
      <EmptyState icon="book" title={t("journal.empty")}>
        {t("journal.empty_detail")}
      </EmptyState>
    );
  }
  const written = new Map(found.data.map((one) => [one.day, one.body]));
  return (
    <>
      {said && <Hint>{said}</Hint>}
      <List>
        {days.map((day) => (
          <ListRow
            key={day}
            icon="book"
            title={dayLabel(day)}
            subtitle={written.get(day) ?? t("journal.unwritten")}
            onClick={() => setOpen(day)}
          />
        ))}
      </List>
      {open && (
        <DaySheet
          day={open}
          body={written.get(open) ?? ""}
          onClose={() => setOpen(null)}
          onSave={async (body) => {
            try {
              setSaid(await saveDay(trip, open, body));
              setOpen(null);
            } catch (error) {
              setSaid(error instanceof Error ? error.message : t("error.save"));
            }
          }}
        />
      )}
    </>
  );
}
