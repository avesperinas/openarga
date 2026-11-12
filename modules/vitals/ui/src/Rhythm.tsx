import { Button, Heading, Hint, List, ListRow, SeriesChart, Skeleton } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Ecg, type EcgTrace, type Irn, Unauthorised, readEcg, readEcgs, readIrns, signIn } from "./api";
import { ecgSeries, irnFoot } from "./rhythm";
import { timeOf } from "./sleep";
import { dayLabel } from "./weight";

export function RhythmCard({ alertsEnabled }: { alertsEnabled: boolean | null }) {
  const [ecgs, setEcgs] = useState<Ecg[] | null>(null);
  const [alerts, setAlerts] = useState<Irn[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [trace, setTrace] = useState<EcgTrace | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    Promise.all([readEcgs(), readIrns()])
      .then(([found, raised]) => {
        setEcgs(found);
        setAlerts(raised);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer el ritmo del corazón.");
      });
  }, []);

  useEffect(() => {
    if (!chosen) return;
    setTrace(null);
    readEcg(chosen)
      .then(setTrace)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudo leer ese electrocardiograma.");
      });
  }, [chosen]);

  if (ecgs !== null && alerts !== null && ecgs.length === 0 && alerts.length === 0 && alertsEnabled === null) return null;
  const drawn = trace ? ecgSeries(trace) : null;

  return (
    <section className="surface vitals-card" aria-label="El ritmo del corazón">
      <Heading>El ritmo del corazón</Heading>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {ecgs === null && !problem && <Skeleton label="Cargando el ritmo del corazón" />}
      {ecgs && ecgs.length > 0 && (
        <List>
          {ecgs.map((one) => (
            <ListRow
              key={one.id}
              title={`ECG del ${dayLabel(one.start.slice(0, 10))}`}
              subtitle={`${timeOf(one.start)} · ${one.result_text ?? "Sin resultado"}`}
              value={one.heart_rate_avg != null ? `${Math.round(one.heart_rate_avg)} lpm` : "—"}
              accessory={one.id === chosen ? "done" : "chevron-right"}
              aria-pressed={one.id === chosen}
              onClick={() => setChosen(one.id)}
            />
          ))}
        </List>
      )}
      {chosen && trace === null && !problem && <Skeleton label="Cargando la traza" />}
      {trace && drawn && (
        <>
          <SeriesChart
            label={`Traza del electrocardiograma del ${dayLabel(trace.start.slice(0, 10))}, en milivoltios`}
            kind="lines"
            labels={drawn.labels}
            series={drawn.series}
            format={(value) => `${value.toLocaleString("es-ES", { maximumFractionDigits: 2 })} mV`}
          />
          <div className="vitals-actions">
            <Button variant="plain" onClick={() => setChosen(null)}>
              Cerrar la traza
            </Button>
          </div>
        </>
      )}
      {alerts && alerts.length > 0 && (
        <List>
          {alerts.map((one) => (
            <ListRow
              key={one.id}
              title="Aviso de ritmo irregular"
              subtitle={[`${dayLabel(one.start.slice(0, 10))}, ${timeOf(one.start)} – ${timeOf(one.end)}`, irnFoot(one)]
                .filter(Boolean)
                .join(" · ")}
            />
          ))}
        </List>
      )}
      {alertsEnabled === false && (
        <Hint>Los avisos de ritmo irregular están desactivados en la app de la pulsera.</Hint>
      )}
      <Hint>Es lo que dijo la pulsera, tal cual. Vitals no lo interpreta ni diagnostica.</Hint>
    </section>
  );
}
