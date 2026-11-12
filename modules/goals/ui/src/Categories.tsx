import {
  Button,
  ConfirmDelete,
  CreateButton,
  EmptyState,
  Hint,
  Icon,
  List,
  ListRow,
  Screen,
  Sheet,
  TextField,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import {
  type Category,
  type Space,
  createCategory,
  createSpace,
  inviteToSpace,
  joinSpace,
  orderCategories,
  readSpaces,
  removeCategory,
  shareCategory,
  updateCategory,
} from "./api";
import { ScreenHeader } from "./Header";
import { Problem, useBusy, useCategories } from "./Parts";
import { HUES, count } from "./words";

export function CategoriesScreen() {
  const { list, reload } = useCategories();
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [sharing, setSharing] = useState<Category | null>(null);

  useEffect(reload, [reload]);

  const current = editing && editing !== "new" ? list.find((one) => one.id === editing.id) : undefined;

  return (
    <Screen>
      <ScreenHeader title="Categorías" />
      {list.length === 0 ? (
        <EmptyState
          icon="layers"
          hue={3}
          title="Sin categorías"
          action={{ label: "Crear una", icon: "plus", onClick: () => setEditing("new") }}
        >
          <p>Cada tarea va en una: Trabajo, Casa, lo que te sirva.</p>
        </EmptyState>
      ) : (
        <List>
          {list.map((one) => (
            <ListRow
              key={one.id}
              title={one.name}
              subtitle={
                [
                  count(one.pending, "pendiente", "pendientes"),
                  one.goals ? count(one.goals, "meta", "metas") : null,
                  one.space_id ? "compartida" : null,
                ]
                  .filter(Boolean)
                  .join(" · ")
              }
              hue={one.hue}
              accessory="chevron-right"
              onClick={() => setEditing(one)}
            />
          ))}
        </List>
      )}
      <CreateButton label="Categoría" onClick={() => setEditing("new")} />

      {editing === "new" && (
        <CategorySheet
          onClose={() => setEditing(null)}
          onChanged={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {current && (
        <CategorySheet
          key={current.id}
          category={current}
          all={list}
          onClose={() => setEditing(null)}
          onShare={() => {
            setSharing(current);
            setEditing(null);
          }}
          onChanged={(close = true) => {
            if (close) setEditing(null);
            reload();
          }}
        />
      )}
      {sharing && (
        <ShareSheet
          category={list.find((one) => one.id === sharing.id) ?? sharing}
          onClose={() => setSharing(null)}
          onChanged={reload}
        />
      )}
    </Screen>
  );
}

function HuePicker({ value, onChange }: { value: number; onChange: (hue: number) => void }) {
  return (
    <div className="goals-hues" role="radiogroup" aria-label="Color">
      {HUES.map((hue) => (
        <button
          key={hue.value}
          type="button"
          role="radio"
          className="goals-hue"
          aria-checked={hue.value === value}
          aria-label={hue.label}
          onClick={() => onChange(hue.value)}
        >
          <span className="list-row-dot" data-hue={hue.value} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function CategorySheet({
  category,
  all = [],
  onClose,
  onChanged,
  onShare,
}: {
  category?: Category;
  all?: Category[];
  onClose: () => void;
  onChanged: (close?: boolean) => void;
  onShare?: () => void;
}) {
  const free = HUES.find((hue) => !all.some((one) => one.hue === hue.value))?.value ?? 1;
  const [name, setName] = useState(category?.name ?? "");
  const [hue, setHue] = useState(category?.hue ?? free);
  const [deleting, setDeleting] = useState(false);
  const { busy, error, run } = useBusy();

  const save = () =>
    void run(async () => {
      if (category) await updateCategory(category.id, { name: name.trim(), hue });
      else await createCategory(name.trim(), hue);
      onChanged();
    }, "No se ha podido guardar");

  const move = (step: -1 | 1) =>
    void run(async () => {
      const ids = all.map((one) => one.id);
      const at = ids.indexOf(category!.id);
      const to = at + step;
      if (to < 0 || to >= ids.length) return;
      [ids[at], ids[to]] = [ids[to]!, ids[at]!];
      await orderCategories(ids);
      onChanged(false);
    }, "No se ha podido mover");

  if (deleting && category) {
    return (
      <ConfirmDelete
        title="¿Borrar esta categoría?"
        subject={category.name}
        consequence={
          category.pending > 0
            ? `Se borran también sus tareas: ${count(category.pending, "pendiente", "pendientes")} y las ya hechas.${category.goals ? " Sus metas se quedan, sin categoría." : ""} No se puede deshacer.`
            : `Se borran también sus tareas hechas.${category.goals ? " Sus metas se quedan, sin categoría." : ""} No se puede deshacer.`
        }
        action="Borrar categoría"
        onCancel={() => setDeleting(false)}
        onConfirm={async () => {
          await removeCategory(category.id);
          onChanged();
        }}
      />
    );
  }

  const position = category ? all.findIndex((one) => one.id === category.id) : -1;

  return (
    <Sheet
      title={category ? category.name : "Nueva categoría"}
      onClose={onClose}
      action={{ label: category ? "Guardar" : "Crear", onClick: save, disabled: busy || !name.trim() }}
    >
      <div className="goals-form">
        <TextField label="Nombre" value={name} placeholder="Universidad" autoFocus={!category} onChange={setName} />
        <HuePicker value={hue} onChange={setHue} />
        {category && (
          <>
            <div className="goals-row-actions">
              <Button icon="chevron-up" disabled={busy || position <= 0} onClick={() => move(-1)}>
                Subir
              </Button>
              <Button icon="chevron-down" disabled={busy || position >= all.length - 1} onClick={() => move(1)}>
                Bajar
              </Button>
              <Button icon="people" onClick={onShare}>
                {category.space_id ? "Compartida" : "Compartir"}
              </Button>
            </div>
            <Button variant="destructive" icon="trash" block onClick={() => setDeleting(true)}>
              Borrar categoría
            </Button>
          </>
        )}
        <Problem error={error} />
      </div>
    </Sheet>
  );
}

function ShareSheet({
  category,
  onClose,
  onChanged,
}: {
  category: Category;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [spaces, setSpaces] = useState<Space[] | null>(null);
  const [mode, setMode] = useState<"pick" | "create" | "join">("pick");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [invite, setInvite] = useState<{ space: string; code: string } | null>(null);
  const { busy, error, run } = useBusy();

  const load = () => readSpaces().then(setSpaces);
  useEffect(() => {
    load().catch(() => setSpaces([]));
  }, []);

  const move = (space: string | null) =>
    void run(async () => {
      await shareCategory(category.id, space);
      onChanged();
    }, "No se ha podido compartir");

  return (
    <Sheet title={`Compartir ${category.name}`} onClose={onClose}>
      {mode === "pick" && (
        <div className="goals-form">
          <Hint>Lo que compartes lo ven y lo tachan los del espacio: la categoría y todas sus tareas.</Hint>
          <ul className="goals-options">
            <li>
              <button
                type="button"
                className="goals-option"
                aria-pressed={category.space_id === null}
                disabled={busy}
                onClick={() => move(null)}
              >
                <Icon name="done" />
                <span>
                  <strong>Solo tú</strong>
                </span>
              </button>
            </li>
            {(spaces ?? []).map((space) => (
              <li key={space.id}>
                <button
                  type="button"
                  className="goals-option"
                  aria-pressed={category.space_id === space.id}
                  disabled={busy}
                  onClick={() => move(space.id)}
                >
                  <Icon name="people" />
                  <span>
                    <strong>{space.name}</strong>
                    <span className="goals-option-detail">
                      {space.members === 1 ? "Solo tú, de momento" : `${space.members} personas`}
                    </span>
                  </span>
                </button>
                {space.role === "owner" && (
                  <Button
                    variant="plain"
                    onClick={() =>
                      void run(async () => {
                        const made = await inviteToSpace(space.id);
                        setInvite({ space: space.name, code: made.code });
                      }, "No se ha podido invitar")
                    }
                  >
                    Invitar
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {invite && (
            <div className="goals-invite">
              <span>Código para entrar en {invite.space}. Sirve una vez, durante 48 horas:</span>
              <strong className="goals-code">{invite.code}</strong>
            </div>
          )}
          <div className="goals-row-actions">
            <Button icon="plus" onClick={() => setMode("create")}>
              Nuevo espacio
            </Button>
            <Button onClick={() => setMode("join")}>Tengo un código</Button>
          </div>
        </div>
      )}
      {mode === "create" && (
        <div className="goals-form">
          <TextField label="Nombre del espacio" value={name} placeholder="Casa" autoFocus onChange={setName} />
          <Button
            variant="primary"
            block
            disabled={busy || !name.trim()}
            onClick={() =>
              void run(async () => {
                await createSpace(name.trim());
                await load();
                setMode("pick");
              }, "No se ha podido crear")
            }
          >
            Crear
          </Button>
        </div>
      )}
      {mode === "join" && (
        <div className="goals-form">
          <TextField label="Código" value={code} placeholder="ABCD-EFGH-JKMN" autoFocus onChange={setCode} />
          <Button
            variant="primary"
            block
            disabled={busy || code.replace(/[^a-z0-9]/gi, "").length < 12}
            onClick={() =>
              void run(async () => {
                await joinSpace(code.trim());
                await load();
                setMode("pick");
              }, "Ese código no vale")
            }
          >
            Entrar
          </Button>
        </div>
      )}
      <Problem error={error} />
    </Sheet>
  );
}
