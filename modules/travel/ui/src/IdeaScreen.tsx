import {
  Button,
  CANNOT_UNDO,
  ConfirmDelete,
  GroupLabel,
  Hint,
  IconButton,
  Screen,
} from "@openarga/ui";
import { WorldMap } from "@openarga/ui/world-map";
import { useEffect, useState } from "react";

import {
  type Idea,
  type Space,
  Unauthorised,
  addIdeaPlace,
  archiveIdea,
  deleteIdea,
  planIdea,
  readIdea,
  readSpaces,
  removeIdeaPlace,
  shareIdea,
  signIn,
  updateIdea,
} from "./api";
import type { Navigate } from "./App";
import { ClimateCard } from "./Climate";
import { ScreenHeader } from "./Header";
import { Pending, useLoad } from "./Loads";
import { PlacePicker } from "./PlacePicker";
import { IdeaSheet, PlanSheet } from "./IdeaSheet";
import { SharePicker } from "./SharePicker";
import { MONTHS_SHORT, PHASES, daysRange, euros, flag, monthsLabel, where } from "./words";

export function IdeaScreen({ id, navigate, onChanged }: { id: string; navigate: Navigate; onChanged: () => void }) {
  const loaded = useLoad<Idea>(`idea/${id}`, () => readIdea(id));
  const idea = loaded.data;
  const setIdea = loaded.set;
  const [problem, setProblem] = useState("");
  const [editing, setEditing] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [removing, setRemoving] = useState<Idea["places"][number] | null>(null);
  const [spaces, setSpaces] = useState<Space[]>([]);

  const fail = (error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
  };
  const apply = async (change: Promise<Idea>) => {
    try {
      setIdea(await change);
      setProblem("");
      onChanged();
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  };

  useEffect(() => {
    readSpaces()
      .then(setSpaces)
      .catch(() => setSpaces([]));
  }, [id]);

  const back = { label: "Planes", onClick: () => navigate({ screen: "plans" }) };
  if (!idea) {
    return (
      <Screen>
        <ScreenHeader title="Idea" back={back} />
        <Pending found={loaded.found} label="Cargando la idea" />
      </Screen>
    );
  }

  const located = idea.places.filter((one) => one.place.lat !== null && one.place.lon !== null);
  const facts = [
    idea.budget_eur !== null ? `${euros(idea.budget_eur)} por persona` : null,
    daysRange(idea.days_min, idea.days_max),
    idea.months.length ? monthsLabel(idea.months) : null,
  ].filter(Boolean);

  return (
    <Screen>
      <ScreenHeader eyebrow={`Idea${idea.archived ? " · Archivada" : ""}`} title={idea.title} back={back} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {located.length > 0 && (
        <div className="surface travel-trip-map">
          <WorldMap
            geoBase="/travel/geo/"
            level="country"
            areas={[]}
            places={located.map((one) => ({
              id: one.place.id,
              lon: one.place.lon!,
              lat: one.place.lat!,
              kind: "idea" as const,
              size: 0,
            }))}
            routes={[]}
            focus={located.map((one) => [one.place.lon!, one.place.lat!] as [number, number])}
            label={`Destinos de ${idea.title}`}
          />
        </div>
      )}
      {facts.length > 0 && <p className="travel-idea-facts">{facts.join(" · ")}</p>}
      {idea.months.length > 0 && (
        <ol className="travel-months" aria-label="Meses buenos">
          {MONTHS_SHORT.map((name, index) => (
            <li key={name} data-good={idea.months.includes(index + 1) || undefined}>
              {name}
            </li>
          ))}
        </ol>
      )}
      {idea.notes && <Hint>{idea.notes}</Hint>}
      <ClimateCard
        idea={idea}
        onUseMonths={(months) =>
          void apply(
            updateIdea(idea.id, {
              title: idea.title,
              notes: idea.notes,
              budget_eur: idea.budget_eur !== null ? String(idea.budget_eur) : null,
              days_min: idea.days_min,
              days_max: idea.days_max,
              months,
              tags: idea.tags,
            }),
          )
        }
      />

      <section className="travel-group">
        <GroupLabel>
          Destinos
          {idea.countries.length > 0 && (
            <span className="travel-group-detail">{idea.countries.map(flag).join(" ")}</span>
          )}
        </GroupLabel>
        <ol className="surface travel-day">
          {idea.places.map((one) => (
            <li key={one.id} className="travel-block travel-idea-place">
              <span className="travel-step-text">
                <span className="travel-step-title">
                  {flag(one.place.country_code)} {one.place.name}
                </span>
                <span className="travel-step-detail">{[where(one.place), one.note].filter(Boolean).join(" · ")}</span>
              </span>
              <IconButton icon="trash" label={`Quitar ${one.place.name}`} variant="plain" size="small" onClick={() => setRemoving(one)} />
            </li>
          ))}
          {idea.places.length === 0 && <li className="travel-day-empty">Aún sin destinos</li>}
          <li className="travel-day-add">
            <Button variant="plain" size="small" icon="plus" onClick={() => setAdding(!adding)}>
              Destino
            </Button>
          </li>
        </ol>
        {adding && (
          <PlacePicker
            label="Destino"
            onPick={async (place) => {
              if (await apply(addIdeaPlace(idea.id, place.id))) setAdding(false);
            }}
          />
        )}
      </section>

      {idea.trips.length > 0 && (
        <section className="travel-group">
          <GroupLabel>Viajes que salieron de aquí</GroupLabel>
          <ol className="surface travel-day">
            {idea.trips.map((trip) => (
              <li key={trip.id} className="travel-block">
                <button type="button" className="travel-block-body" onClick={() => navigate({ screen: "trip", id: trip.id })}>
                  <span className="travel-step-text">
                    <span className="travel-step-title">{trip.title}</span>
                    <span className="travel-step-detail">
                      {PHASES[trip.phase]} · {trip.starts_on}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}

      {idea.mine && (
        <section className="travel-group">
          <GroupLabel>Compartida</GroupLabel>
          <SharePicker trip={idea} spaces={spaces} onChoose={async (space) => void (await apply(shareIdea(idea.id, space)))} />
        </section>
      )}

      <div className="travel-actions">
        <Button variant="primary" icon="calendar" onClick={() => setPlanning(true)}>
          Pasar a plan
        </Button>
        <Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>
          Editar
        </Button>
        <Button
          variant="secondary"
          icon={idea.archived ? "undo" : undefined}
          onClick={() => void apply(archiveIdea(idea.id, !idea.archived))}
        >
          {idea.archived ? "Sacar del archivo" : "Archivar"}
        </Button>
        {idea.mine && (
          <Button variant="destructive" icon="trash" onClick={() => setDeleting(true)}>
            Borrar idea
          </Button>
        )}
      </div>

      {editing && (
        <IdeaSheet
          idea={idea}
          onClose={() => setEditing(false)}
          onSave={async (data) => {
            if (await apply(updateIdea(idea.id, data))) setEditing(false);
          }}
        />
      )}
      {planning && (
        <PlanSheet
          idea={idea}
          onClose={() => setPlanning(false)}
          onPlan={async (plan) => {
            try {
              const trip = await planIdea(idea.id, plan);
              onChanged();
              navigate({ screen: "trip", id: trip.id });
            } catch (error) {
              fail(error);
              setPlanning(false);
            }
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title="¿Quitar el destino?"
          subject={removing.place.name}
          consequence="El lugar sigue guardado."
          action="Quitar"
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await apply(removeIdeaPlace(idea.id, removing.id));
            setRemoving(null);
          }}
        />
      )}
      {deleting && (
        <ConfirmDelete
          title="¿Borrar la idea?"
          subject={idea.title}
          consequence={`Se borran sus destinos; los viajes que salieron de ella se quedan. ${CANNOT_UNDO}`}
          action="Borrar idea"
          onCancel={() => setDeleting(false)}
          onConfirm={async () => {
            await deleteIdea(idea.id);
            onChanged();
            navigate({ screen: "plans" });
          }}
        />
      )}
    </Screen>
  );
}
