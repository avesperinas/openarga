import { EmptyState, Screen, Skeleton, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { ApiError, type NextSession, type Today } from "./api";
import { readTodayKept, startAnywhere } from "./offline";
import { ConfirmStartSheet, rotationDetail } from "./ConfirmStart";

export type NextTarget =
  | { session: string }
  | { today: true }
  | { confirm: NextSession; days?: { id: string; name: string; done: boolean }[] };

export async function resolveNext(read: () => Promise<Today> = readTodayKept): Promise<NextTarget> {
  const today = await read();
  if (today.in_progress) return { session: today.in_progress };
  if (!today.next) return { today: true };
  const days = today.rotation?.days.map((day) => ({ id: day.plan_day_id, name: day.name, done: day.done }));
  return days ? { confirm: today.next, days } : { confirm: today.next };
}

export async function startNext(
  read: () => Promise<Today> = readTodayKept,
  start: () => Promise<string> = () => startAnywhere(),
): Promise<string> {
  try {
    return await start();
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      const fresh = await read();
      if (fresh.in_progress) return fresh.in_progress;
    }
    throw error;
  }
}

export function NextRedirect({ onSession, onToday }: { onSession: (id: string) => void; onToday: () => void }) {
  const t = useT();
  const [failed, setFailed] = useState(false);
  const [confirm, setConfirm] = useState<NextSession | null>(null);
  const [days, setDays] = useState<{ id: string; name: string; done: boolean }[] | undefined>();
  const [chosen, setChosen] = useState<string | null>(null);
  useEffect(() => {
    resolveNext()
      .then((target) => {
        if ("session" in target) onSession(target.session);
        else if ("confirm" in target) {
          setConfirm(target.confirm);
          setDays(target.days);
        }
        else onToday();
      })
      .catch(() => setFailed(true));
  }, [onSession, onToday]);
  return (
    <Screen>
      {failed ? (
        <EmptyState title={t("next.open_failed")}>{t("next.open_failed_hint")}</EmptyState>
      ) : (
        <Skeleton rows={3} label={t("next.opening")} />
      )}
      {confirm && (
        <ConfirmStartSheet
          name={days?.find((day) => day.id === chosen)?.name ?? confirm.name}
          days={days}
          chosen={chosen ?? confirm.plan_day_id}
          onChoose={setChosen}
          detail={rotationDetail(
            t,
            confirm.rotation_number,
            confirm.days_in_rotation - confirm.remaining + 1,
            confirm.days_in_rotation,
          )}
          onCancel={onToday}
          onStart={async () =>
            onSession(
              await startNext(readTodayKept, () =>
                startAnywhere(chosen && chosen !== confirm.plan_day_id ? chosen : undefined),
              ),
            )
          }
        />
      )}
    </Screen>
  );
}
