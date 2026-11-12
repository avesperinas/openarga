import { Button, Hint, List, ListRow, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Candidate, type Place, readPlaces, savePlace, searchPlaces } from "./api";
import { flag, where } from "./words";

export function PlacePicker({ label, onPick }: { label: string; onPick: (place: Place) => void }) {
  const [query, setQuery] = useState("");
  const [saved, setSaved] = useState<Place[]>([]);
  const [found, setFound] = useState<Candidate[] | null>(null);
  const [failed, setFailed] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setFound(null);
    setFailed("");
    const text = query.trim();
    if (text.length < 2) {
      setSaved([]);
      return;
    }
    const timer = window.setTimeout(() => {
      readPlaces(text)
        .then(setSaved)
        .catch(() => setSaved([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [query]);

  const search = async () => {
    const text = query.trim();
    if (text.length < 2 || busy) return;
    setBusy(true);
    setFailed("");
    try {
      const answer = await searchPlaces(text);
      setFound(answer.candidates);
      if (answer.failed.length) setFailed(answer.failed.map((one) => one.reason).join(" · "));
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "No se ha podido buscar.");
    } finally {
      setBusy(false);
    }
  };

  const pick = async (candidate: Partial<Candidate> & { name: string }) => {
    setBusy(true);
    try {
      onPick(await savePlace(candidate));
      setQuery("");
    } catch (error) {
      setFailed(error instanceof Error ? error.message : "No se ha podido guardar el lugar.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="travel-picker">
      <TextField
        label={label}
        type="search"
        value={query}
        onChange={setQuery}
        onSubmit={() => void search()}
        placeholder="Brujas, Museo del Prado, Santiago de Chile…"
      />
      {saved.length > 0 && (
        <List>
          {saved.slice(0, 5).map((place) => (
            <ListRow
              key={place.id}
              title={`${flag(place.country_code)} ${place.name}`}
              detail={[place.region, place.country].filter(Boolean).join(", ") || "Sin situar"}
              accessory="plus"
              onClick={() => onPick(place)}
            />
          ))}
        </List>
      )}
      {query.trim().length >= 2 && (
        <Button variant="secondary" icon="globe" onClick={() => void search()} disabled={busy}>
          {busy ? "Buscando…" : "Buscar en OpenStreetMap"}
        </Button>
      )}
      {found && found.length > 0 && (
        <List>
          {found.map((candidate) => (
            <ListRow
              key={`${candidate.osm_type}${candidate.osm_id}`}
              title={`${flag(candidate.country_code)} ${candidate.name}`}
              detail={where(candidate) === candidate.name ? candidate.display_name : where(candidate)}
              subtitle={candidate.kind}
              accessory="plus"
              disabled={busy}
              onClick={() => void pick(candidate)}
            />
          ))}
        </List>
      )}
      {found && found.length === 0 && !failed && <Hint>OpenStreetMap no conoce ese nombre.</Hint>}
      {failed && (
        <Hint tone="warning">
          {failed}
        </Hint>
      )}
      {(failed || (found && found.length === 0)) && query.trim() && (
        <Button variant="plain" onClick={() => void pick({ name: query.trim() })} disabled={busy}>
          Guardar «{query.trim()}» sin situar en el mapa
        </Button>
      )}
    </div>
  );
}
