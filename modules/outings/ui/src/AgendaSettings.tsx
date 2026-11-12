import { Button, ConfirmDelete, Hint, List, ListRow, OfflineNotice, Section, TextField } from "@openarga/ui";
import { useState } from "react";

import {
  type Interest,
  type PluggedSource,
  addInterest,
  readInterests,
  readSources,
  removeInterest,
  unplugSource,
} from "./api";
import { Pending, changed, useLoad } from "./Loads";
import { UpdateSheet } from "./UpdateSheet";
import { since } from "./words";

export function AgendaSettings() {
  const plugged = useLoad("sources", readSources).data?.plugged ?? [];
  const { data: interests, found } = useLoad("interests", readInterests);
  const [liked, setLiked] = useState("");
  const [muted, setMuted] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [removing, setRemoving] = useState<PluggedSource | null>(null);
  const [updating, setUpdating] = useState(false);

  const refresh = changed;

  async function add(kind: Interest["kind"], term: string) {
    if (term.trim().length < 2) return;
    setProblem(null);
    try {
      await addInterest(kind, term.trim());
      if (kind === "like") setLiked("");
      else setMuted("");
      refresh();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
    }
  }

  async function remove(one: Interest) {
    try {
      await removeInterest(one.id);
      refresh();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "No se ha podido quitar.");
    }
  }

  const of = (kind: Interest["kind"]) => (interests ?? []).filter((one) => one.kind === kind);

  return (
    <>
      <OfflineNotice />
      <Section title="Agenda">
        <Hint>
          La llena tu Claude con tu suscripción: una tarea programada cada semana, o tú cuando quieras desde Actualizar.
          Apunta las fiestas y los festivales enteros, con su programa, y deja fuera congresos, festivos y lo que no es
          ocio.
        </Hint>
        <Button variant="secondary" icon="copy" onClick={() => setUpdating(true)}>
          Actualizar con Claude
        </Button>
        {plugged.length > 0 && (
          <>
            <Hint tone="warning">
              Esta agenda sigue enchufada con tu clave de la API y gasta cada madrugada. Quítala: lo que guardaste se
              queda.
            </Hint>
            <List>
              {plugged.map((source) => (
                <ListRow
                  key={source.connection}
                  title={source.label}
                  subtitle={source.last_run_at ? `Leída ${since(source.last_run_at)}` : undefined}
                  tone="warning"
                  icon="calendar"
                  hue={5}
                  action={{ icon: "trash", label: `Quitar ${source.label}`, onClick: () => setRemoving(source) }}
                />
              ))}
            </List>
          </>
        )}
      </Section>

      {interests === null && <Pending found={found} rows={3} />}

      <Section title="Me interesa" count={of("like").length || undefined}>
        <Hint>Sube en Explorar y tu Claude lo busca a propósito.</Hint>
        {of("like").length > 0 && <Terms terms={of("like")} onRemove={(one) => void remove(one)} />}
        <TextField label="Añadir" value={liked} onChange={setLiked} onSubmit={() => void add("like", liked)} placeholder="Jazz, Baluarte, setas…" />
        {liked.trim() && (
          <Button variant="secondary" icon="plus" onClick={() => void add("like", liked)}>
            Añadir
          </Button>
        )}
      </Section>

      <Section title="No me interesa" count={of("mute").length || undefined}>
        <Hint>Lo que lo lleve no sale en Explorar ni en la Agenda, ni lo apunta tu Claude.</Hint>
        {of("mute").length > 0 && <Terms terms={of("mute")} onRemove={(one) => void remove(one)} />}
        <TextField label="Silenciar" value={muted} onChange={setMuted} onSubmit={() => void add("mute", muted)} placeholder="Congreso, cuentacuentos…" />
        {muted.trim() && (
          <Button variant="secondary" icon="plus" onClick={() => void add("mute", muted)}>
            Silenciar
          </Button>
        )}
      </Section>

      {problem && <Hint tone="warning">{problem}</Hint>}

      {updating && <UpdateSheet onClose={() => setUpdating(false)} />}

      {removing && (
        <ConfirmDelete
          title="¿Quitar esta agenda?"
          subject={removing.label}
          consequence="Deja de leerse con tu clave, y lo que trajo y no guardaste deja de salir. Lo que apunta tu Claude se queda."
          action="Quitar agenda"
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await unplugSource(removing.connection);
            setRemoving(null);
            refresh();
          }}
        />
      )}
    </>
  );
}

function Terms({ terms, onRemove }: { terms: Interest[]; onRemove: (one: Interest) => void }) {
  return (
    <List>
      {terms.map((one) => (
        <ListRow
          key={one.id}
          title={one.term}
          icon={one.kind === "like" ? "heart" : "eye-off"}
          hue={one.kind === "like" ? 7 : 8}
          action={{ icon: "close", label: `Quitar ${one.term}`, onClick: () => onRemove(one) }}
        />
      ))}
    </List>
  );
}
