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
    setPreparing("Preparando el viaje para usarlo sin conexión…");
    prepare(id, (done, total) => setPreparing(`Guardando el viaje sin conexión: ${done} de ${total}`))
      .then((failed) => {
        markPrepared(id);
        setPreparing(failed ? `Guardado sin conexión, salvo ${failed} cosa(s).` : "Listo: todo el viaje funciona sin conexión.");
      })
      .catch((error: unknown) =>
        setPreparing(error instanceof Error ? `No se ha guardado sin conexión: ${error.message}` : ""),
      );
  }, [id, installed, loaded]);

  if (!trip) {
    return (
      <Screen>
        <ScreenHeader title="Viaje" />
        <Pending found={read.found} label="Cargando el viaje" />
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
            Para tener este viaje como app: en Safari, Compartir → «Añadir a pantalla de inicio». Se abre a pantalla
            completa, con su portada de icono y todo el viaje sin conexión.
          </Hint>
        </div>
      )}
      <TripScreen id={trip.id} tab="trip" home={null} navigate={navigate} onChanged={() => undefined} />
    </>
  );
}
