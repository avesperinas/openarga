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
import { say } from "../words";

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
    <Section title={say("spaces.title")}>
      <Hint>{say("spaces.hint")}</Hint>
      {failed ? (
        <Notice tone="negative" action={onRetry && { label: say("spaces.retry"), onClick: onRetry }}>
          {say("spaces.failed")}
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
          {say("spaces.new")}
        </Button>
        <Button onClick={onJoin}>{say("spaces.have_code")}</Button>
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
      setError(problem instanceof Error ? problem.message : say("spaces.error"));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

function Problem({ error }: { error: string | null }) {
  return error ? <Notice tone="negative">{error}</Notice> : null;
}

function NewSpaceSheet({ onClose, onDone }: { onClose: () => void; onDone: (space: Space) => void }) {
  const [name, setName] = React.useState("");
  const [me, setMe] = React.useState("");
  const { busy, error, run } = useBusy();
  const ready = name.trim() !== "" && me.trim() !== "" && !busy;
  const submit = () => ready && void run(async () => onDone(await createSpace(name, me)));
  return (
    <Sheet title={say("spaces.new")} onClose={onClose} action={{ label: say("spaces.create"), onClick: submit, disabled: !ready }}>
      <div className="settings-fields">
        <TextField label={say("spaces.name")} value={name} placeholder={say("spaces.name.placeholder")} autoFocus onChange={setName} />
        <TextField label={say("spaces.me")} value={me} hint={say("spaces.name.hint")} onChange={setMe} onSubmit={submit} />
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
    <Sheet title={say("spaces.join")} onClose={onClose} action={{ label: say("spaces.join.action"), onClick: submit, disabled: !ready }}>
      <div className="settings-fields">
        <TextField label={say("spaces.code")} value={code} placeholder="ABCD-EFGH-JKMN" autoFocus onChange={setCode} />
        <TextField label={say("spaces.me")} value={me} hint={say("spaces.name.hint")} onChange={setMe} onSubmit={submit} />
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
          label={say("spaces.my_name")}
          value={me}
          placeholder={say("spaces.unnamed")}
          hint={say("spaces.name.hint")}
          onChange={setMe}
          onBlur={saveName}
          onSubmit={saveName}
        />
      </div>

      <h3 className="sheet-group">{say("spaces.members")}</h3>
      <List>
        {space.members.map((member) => {
          const self = member.user_id === space.me;
          return (
            <ListRow
              key={member.user_id}
              title={memberLabel(space, member)}
              detail={member.role === "owner" ? say("spaces.owner") : undefined}
              action={
                owner && !self
                  ? { icon: "minus", label: say("spaces.remove", { name: memberLabel(space, member) }), onClick: () => setRemoving(member) }
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
              <CopyField label={say("spaces.invite.code")} value={invite.code} />
              <Hint>{say("spaces.invite.hint")}</Hint>
            </>
          ) : (
            <Button
              icon="plus"
              block
              disabled={busy}
              onClick={() => void run(async () => setInvite(await inviteTo(space.id)))}
            >
              {say("spaces.invite")}
            </Button>
          )}
        </>
      )}

      {alone ? (
        <Hint>{say("spaces.alone")}</Hint>
      ) : (
        <Button variant="destructive" block disabled={busy} onClick={() => setRemoving(space.members.find((m) => m.user_id === space.me) ?? null)}>
          {say("spaces.leave")}
        </Button>
      )}

      <Problem error={error} />

      {removing && (
        <ConfirmDelete
          title={removing.user_id === space.me ? say("spaces.leave.title", { space: space.name }) : say("spaces.remove.title", { name: memberLabel(space, removing) })}
          consequence={
            removing.user_id === space.me
              ? say("spaces.leave.consequence")
              : say("spaces.remove.consequence")
          }
          action={removing.user_id === space.me ? say("spaces.leave.action") : say("spaces.remove.action")}
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
