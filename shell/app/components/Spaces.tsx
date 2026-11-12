"use client";

import {
  Button,
  ConfirmDelete,
  CopyField,
  Hint,
  List,
  ListRow,
  Notice,
  Section,
  Sheet,
  TextField,
} from "@openarga/ui";
import * as React from "react";

import {
  type Invite,
  type Space,
  type SpaceMember,
  createSpace,
  inviteTo,
  joinSpace,
  looksLikeCode,
  memberLabel,
  membersLine,
  myName,
  readSpaces,
  removeMember,
  renameMe,
} from "../lib/spaces";

type Open =
  | { kind: "create" }
  | { kind: "join" }
  | { kind: "space"; id: string }
  | null;

export function Spaces() {
  const [spaces, setSpaces] = React.useState<Space[] | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [open, setOpen] = React.useState<Open>(null);

  const load = React.useCallback(
    () =>
      readSpaces()
        .then((found) => {
          setSpaces(found);
          setFailed(false);
        })
        .catch(() => setFailed(true)),
    [],
  );
  React.useEffect(() => {
    void load();
  }, [load]);

  const replace = (space: Space) =>
    setSpaces((current) => {
      const list = current ?? [];
      return list.some((one) => one.id === space.id)
        ? list.map((one) => (one.id === space.id ? space : one))
        : [...list, space];
    });
  const shown = open?.kind === "space" ? spaces?.find((one) => one.id === open.id) : undefined;

  return (
    <SpacesView
      spaces={spaces}
      failed={failed}
      onRetry={() => void load()}
      onOpen={(id) => setOpen({ kind: "space", id })}
      onCreate={() => setOpen({ kind: "create" })}
      onJoin={() => setOpen({ kind: "join" })}
    >
      {open?.kind === "create" && (
        <NewSpaceSheet
          onClose={() => setOpen(null)}
          onDone={(space) => {
            replace(space);
            setOpen({ kind: "space", id: space.id });
          }}
        />
      )}
      {open?.kind === "join" && (
        <JoinSheet
          onClose={() => setOpen(null)}
          onDone={(space) => {
            replace(space);
            setOpen({ kind: "space", id: space.id });
          }}
        />
      )}
      {shown && (
        <SpaceSheet
          space={shown}
          onClose={() => setOpen(null)}
          onChanged={replace}
          onLeft={() => {
            setOpen(null);
            void load();
          }}
        />
      )}
    </SpacesView>
  );
}

export function SpacesView({
  spaces,
  failed = false,
  onRetry,
  onOpen,
  onCreate,
  onJoin,
  children,
}: {
  spaces: Space[] | null;
  failed?: boolean;
  onRetry?: () => void;
  onOpen?: (id: string) => void;
  onCreate?: () => void;
  onJoin?: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Section title="Espacios">
      <Hint>
        Un espacio es un grupo de personas que ven lo mismo, como la lista de la compra de casa.
        Se entra con un código que das tú: nadie puede encontrarte sin él.
      </Hint>
      {failed ? (
        <Notice tone="negative" action={onRetry && { label: "Reintentar", onClick: onRetry }}>
          No se han podido traer tus espacios.
        </Notice>
      ) : spaces && spaces.length > 0 ? (
        <List>
          {spaces.map((space) => (
            <ListRow
              key={space.id}
              icon="people"
              title={space.name}
              subtitle={membersLine(space)}
              accessory="chevron-right"
              onClick={() => onOpen?.(space.id)}
            />
          ))}
        </List>
      ) : null}
      <div className="settings-actions">
        <Button icon="plus" onClick={onCreate}>
          Nuevo espacio
        </Button>
        <Button onClick={onJoin}>Tengo un código</Button>
      </div>
      {children}
    </Section>
  );
}

function useBusy() {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "No se ha podido hacer.");
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function Problem({ error }: { error: string | null }) {
  return error ? <Notice tone="negative">{error}</Notice> : null;
}

const NAME_HINT = "Lo ven solo los de este espacio. Puede ser distinto en cada uno.";

function NewSpaceSheet({ onClose, onDone }: { onClose: () => void; onDone: (space: Space) => void }) {
  const [name, setName] = React.useState("");
  const [me, setMe] = React.useState("");
  const { busy, error, run } = useBusy();
  const ready = name.trim() !== "" && me.trim() !== "" && !busy;
  const submit = () => ready && void run(async () => onDone(await createSpace(name, me)));
  return (
    <Sheet title="Nuevo espacio" onClose={onClose} action={{ label: "Crear", onClick: submit, disabled: !ready }}>
      <div className="settings-fields">
        <TextField label="Nombre del espacio" value={name} placeholder="Casa" autoFocus onChange={setName} />
        <TextField label="Cómo te llaman ahí" value={me} hint={NAME_HINT} onChange={setMe} onSubmit={submit} />
      </div>
      <Problem error={error} />
    </Sheet>
  );
}

function JoinSheet({ onClose, onDone }: { onClose: () => void; onDone: (space: Space) => void }) {
  const [code, setCode] = React.useState("");
  const [me, setMe] = React.useState("");
  const { busy, error, run } = useBusy();
  const ready = looksLikeCode(code) && me.trim() !== "" && !busy;
  const submit = () => ready && void run(async () => onDone(await joinSpace(code, me)));
  return (
    <Sheet title="Entrar con un código" onClose={onClose} action={{ label: "Entrar", onClick: submit, disabled: !ready }}>
      <div className="settings-fields">
        <TextField label="Código" value={code} placeholder="ABCD-EFGH-JKMN" autoFocus onChange={setCode} />
        <TextField label="Cómo te llaman ahí" value={me} hint={NAME_HINT} onChange={setMe} onSubmit={submit} />
      </div>
      <Problem error={error} />
    </Sheet>
  );
}

export function SpaceSheet({
  space,
  onClose,
  onChanged,
  onLeft,
}: {
  space: Space;
  onClose: () => void;
  onChanged: (space: Space) => void;
  onLeft: () => void;
}) {
  const [me, setMe] = React.useState(myName(space));
  const [invite, setInvite] = React.useState<Invite | null>(null);
  const [removing, setRemoving] = React.useState<SpaceMember | null>(null);
  const { busy, error, run } = useBusy();
  const owner = space.role === "owner";
  const alone = space.members.length === 1;

  const saveName = () => {
    if (me.trim() === "" || me.trim() === myName(space)) return;
    void run(async () => onChanged(await renameMe(space.id, me)));
  };

  return (
    <Sheet title={space.name} onClose={onClose}>
      <div className="settings-fields">
        <TextField
          label="Tu nombre en este espacio"
          value={me}
          placeholder="Sin nombre"
          hint={NAME_HINT}
          onChange={setMe}
          onBlur={saveName}
          onSubmit={saveName}
        />
      </div>

      <h3 className="sheet-group">Quién está</h3>
      <List>
        {space.members.map((member) => {
          const self = member.user_id === space.me;
          return (
            <ListRow
              key={member.user_id}
              title={memberLabel(space, member)}
              detail={member.role === "owner" ? "Dueño" : undefined}
              action={
                owner && !self
                  ? { icon: "minus", label: `Quitar a ${memberLabel(space, member)}`, onClick: () => setRemoving(member) }
                  : undefined
              }
            />
          );
        })}
      </List>

      {owner && (
        <>
          {invite ? (
            <>
              <CopyField label="Código para entrar" value={invite.code} />
              <Hint>Sirve una vez y caduca en 48 horas. Dáselo a quien quieras que entre.</Hint>
            </>
          ) : (
            <Button
              icon="plus"
              block
              disabled={busy}
              onClick={() => void run(async () => setInvite(await inviteTo(space.id)))}
            >
              Invitar a alguien
            </Button>
          )}
        </>
      )}

      {alone ? (
        <Hint>Eres la única persona del espacio, así que no puedes salir: se quedaría sin nadie.</Hint>
      ) : (
        <Button variant="destructive" block disabled={busy} onClick={() => setRemoving(space.members.find((m) => m.user_id === space.me) ?? null)}>
          Salir del espacio
        </Button>
      )}

      <Problem error={error} />

      {removing && (
        <ConfirmDelete
          title={removing.user_id === space.me ? `¿Salir de ${space.name}?` : `¿Quitar a ${memberLabel(space, removing)}?`}
          consequence={
            removing.user_id === space.me
              ? "Dejarás de ver lo que hay en el espacio, también lo de antes. Los demás lo conservan. Para volver te tendrán que invitar."
              : "Dejará de ver lo que hay en el espacio, también lo de antes. Para volver le tendrás que invitar."
          }
          action={removing.user_id === space.me ? "Salir" : "Quitar"}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await removeMember(space.id, removing.user_id);
            const self = removing.user_id === space.me;
            setRemoving(null);
            if (self) onLeft();
            else
              onChanged({
                ...space,
                members: space.members.filter((member) => member.user_id !== removing.user_id),
              });
          }}
        />
      )}
    </Sheet>
  );
}
