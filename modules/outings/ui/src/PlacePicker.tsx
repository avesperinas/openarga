import { Button, Hint, List, ListRow, TextField } from "@openarga/ui";
import { useState } from "react";

import { type Place, type PlaceCandidate, searchPlaces } from "./api";
import { t } from "./lang";
import { placeLine } from "./words";

export function PlacePicker({
  placeholder,
  onPick,
}: {
  placeholder: string;
  onPick: (place: Place) => void;
}) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<PlaceCandidate[] | null>(null);
  const [failed, setFailed] = useState("");
  const [busy, setBusy] = useState(false);

  const search = async () => {
    const text = query.trim();
    if (text.length < 2 || busy) return;
    setBusy(true);
    setFailed("");
    setFound(null);
    try {
      const answer = await searchPlaces(text);
      setFound(answer.candidates);
      if (answer.failed.length) setFailed(answer.failed.map((one) => one.reason).join(" · "));
    } catch (error) {
      setFailed(error instanceof Error ? error.message : t("problem.search"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="outings-fields">
      <TextField
        label={t("place.label")}
        type="search"
        value={query}
        onChange={setQuery}
        onSubmit={() => void search()}
        placeholder={placeholder}
      />
      {query.trim().length >= 2 && (
        <Button variant="secondary" icon="search" onClick={() => void search()} disabled={busy}>
          {busy ? t("place.searching") : t("place.search")}
        </Button>
      )}
      {found && found.length > 0 && (
        <List>
          {found.map((candidate) => (
            <ListRow
              key={candidate.osm_ref ?? `${candidate.name}${candidate.lat}`}
              title={candidate.name}
              subtitle={placeLine(candidate)}
              detail={candidate.kind ?? undefined}
              accessory="plus"
              onClick={() => onPick(withoutKind(candidate))}
            />
          ))}
        </List>
      )}
      {found && found.length === 0 && !failed && <Hint>{t("place.unknown")}</Hint>}
      {failed && <Hint tone="warning">{failed}</Hint>}
      {(failed || (found && found.length === 0)) && query.trim() && (
        <Button variant="plain" onClick={() => onPick({ name: query.trim() })}>
          {t("place.keep_name", { name: query.trim() })}
        </Button>
      )}
    </div>
  );
}

function withoutKind(candidate: PlaceCandidate): Place {
  const place: PlaceCandidate = { ...candidate };
  delete place.kind;
  return place;
}
