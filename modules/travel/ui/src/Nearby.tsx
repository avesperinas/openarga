import { Button, ChoiceChips, Hint, Sheet, Skeleton } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type NearbyKind, type NearbyPlace, Unauthorised, readNearby, signIn } from "./api";
import { distance } from "./words";

export interface Around {
  lat: number;
  lon: number;
  label: string;
  day: string | null;
  dayLabel: string | null;
}

const KINDS: { value: NearbyKind; label: string }[] = [
  { value: "sights", label: "Qué ver" },
  { value: "food", label: "Comer" },
  { value: "nature", label: "Naturaleza" },
  { value: "shopping", label: "Compras" },
  { value: "nightlife", label: "Noche" },
];

const RADII: { value: string; label: string }[] = [
  { value: "500", label: "500 m" },
  { value: "1000", label: "1 km" },
  { value: "3000", label: "3 km" },
];

export function NearbySheet({
  around,
  onClose,
  onKeep,
}: {
  around: Around;
  onClose: () => void;
  onKeep: (place: NearbyPlace, day: string | null) => Promise<boolean>;
}) {
  const [kind, setKind] = useState<NearbyKind>("sights");
  const [radius, setRadius] = useState("1000");
  const [found, setFound] = useState<NearbyPlace[] | null>(null);
  const [problem, setProblem] = useState("");
  const [kept, setKept] = useState<Set<string>>(new Set());

  useEffect(() => {
    let current = true;
    setFound(null);
    setProblem("");
    readNearby(around.lat, around.lon, kind, Number(radius))
      .then((answer) => {
        if (!current) return;
        setFound(answer.places);
        if (answer.failed) setProblem(answer.failed);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (current) setProblem(error instanceof Error ? error.message : "No se ha podido preguntar.");
      });
    return () => {
      current = false;
    };
  }, [around.lat, around.lon, kind, radius]);

  const keep = async (place: NearbyPlace, day: string | null) => {
    if (await onKeep(place, day)) setKept(new Set([...kept, `${place.osm_type}/${place.osm_id}`]));
  };

  return (
    <Sheet title={`Cerca de ${around.label}`} onClose={onClose}>
      <div className="travel-sheet-stack">
        <ChoiceChips label="Qué buscas" value={kind} onChange={setKind} options={KINDS} />
        <ChoiceChips label="Hasta" value={radius} onChange={setRadius} options={RADII} />
        {problem && <Hint tone="warning">{problem}</Hint>}
        {found === null && !problem && <Skeleton label="Buscando cerca" />}
        {found !== null && found.length === 0 && !problem && <Hint>No hay nada de eso tan cerca.</Hint>}
        {found !== null && found.length > 0 && (
          <ol className="surface travel-day">
            {found.map((one) => {
              const done = kept.has(`${one.osm_type}/${one.osm_id}`);
              return (
                <li key={`${one.osm_type}/${one.osm_id}`} className="travel-block travel-nearby">
                  <span className="travel-step-text">
                    <span className="travel-step-title">{one.name}</span>
                    <span className="travel-step-detail">
                      {[distance(one.distance_m), one.local_name, one.cuisine, one.opening_hours]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <span className="travel-nearby-actions">
                    {done ? (
                      <span className="travel-step-detail">Guardado</span>
                    ) : (
                      <>
                        <Button variant="plain" size="small" onClick={() => void keep(one, null)}>
                          Guardar
                        </Button>
                        {around.day && (
                          <Button variant="tinted" size="small" onClick={() => void keep(one, around.day)}>
                            {around.dayLabel ?? "Al día"}
                          </Button>
                        )}
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
        <p className="travel-footnote">Datos de OpenStreetMap.</p>
      </div>
    </Sheet>
  );
}
