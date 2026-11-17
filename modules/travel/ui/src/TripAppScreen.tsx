import { Hint, Screen } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Trip, readTrip } from "./api";
import type { Navigate } from "./App";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { prepare } from "./prepare";
import { TodayScreen } from "./Today";
import { dressAs, markPrepared, preparedOnce, standalone } from "./tripApp";
import { TripScreen } from "./TripScreen";
import { t } from "./lang";

export function TripAppScreen({ id, navigate }: { id: string; navigate: Navigate }) {
  const read = useLoad<Trip>(`trip/${id}`, () => readTrip(id));
  const trip = read.data;
  const [preparing, setPreparing] = useState("");
  const installed = standalone();

  useEffect(() => {
    if (trip) void dressAs(trip);
  }, [trip]);

  const loaded = trip !== null;
  useEffect(() => {
    if (!loaded || !installed || !navigator.onLine || preparedOnce(id)) return;
    setPreparing(t("tripapp.preparing"));
    prepare(id, (done, total) => setPreparing(t("tripapp.saving", { done, total })))
      .then((failed) => {
        markPrepared(id);
        setPreparing(failed ? t("tripapp.partial", { failed }) : t("tripapp.done"));
      })
      .catch((error: unknown) =>
        setPreparing(error instanceof Error ? t("tripapp.failed", { reason: error.message }) : ""),
      );
  }, [id, installed, loaded]);

  if (!trip) {
    return (
      <Screen>
        <ScreenHeader title={t("trip.title")} />
        <Pending found={read.found} label={t("trip.loading")} />
      </Screen>
    );
  }
  const note = preparing && <div className="travel-preparing glass" role="status">{preparing}</div>;
  if (installed && trip.phase === "ongoing") {
    return (
      <>
        {note}
        <TodayScreen navigate={navigate} tripId={trip.id} />
      </>
    );
  }
  return (
    <>
      {note}
      {!installed && (
        <div className="travel-install-hint">
          <Hint>
            {t("tripapp.install_hint")}
          </Hint>
        </div>
      )}
      <TripScreen id={trip.id} tab="trip" home={null} navigate={navigate} onChanged={() => undefined} />
    </>
  );
}
