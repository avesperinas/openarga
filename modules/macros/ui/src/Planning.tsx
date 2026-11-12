import { useResource } from "@openarga/app";
import { Button, Card, ConfirmPanel, Hint, List, ListRow, Notice, Sheet, TextField, useToast } from "@openarga/ui";
import { useEffect, useState } from "react";

import {
  type Entry,
  type Outdated,
  type Template,
  readOutdated,
  readTemplates,
  recalculateRecipe,
  removeTemplate,
  saveTemplate,
  templateFromEntry,
} from "./api";

export function dailyLabel(template: Pick<Template, "daily_at">): string | undefined {
  return template.daily_at ? `cada día a las ${template.daily_at.slice(0, 5)}` : undefined;
}

export function outdatedLabel(one: Outdated): string {
  return `${one.name}: ${one.items} ${one.items === 1 ? "registro" : "registros"} con la versión anterior`;
}

function failed(toast: ReturnType<typeof useToast>, reason: unknown, fallback: string) {
  toast({ message: reason instanceof Error ? reason.message : fallback, tone: "error" });
}

export function SaveTemplateSheet({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const [name, setName] = useState(entry.said ?? entry.items.map((item) => item.name).join(" + "));
  const [at, setAt] = useState("");
  const toast = useToast();
  const valid = /^([01]\d|2[0-3]):[0-5]\d$/.test(at.trim());
  const save = () =>
    void templateFromEntry(entry.id, name.trim(), valid ? at.trim() : null)
      .then(() => {
        toast({ message: "Menú guardado" });
        onClose();
      })
      .catch((reason: unknown) => failed(toast, reason, "No se ha podido guardar"));
  return (
    <Sheet
      title="Guardar como menú"
      onClose={onClose}
      action={{ label: "Guardar", onClick: save, disabled: !name.trim() || (at.trim() !== "" && !valid) }}
    >
      <TextField label="Nombre" value={name} onChange={setName} autoFocus />
      <TextField label="Cada día a las (opcional)" type="time" value={at} onChange={setAt} />
      <Hint>Con hora, cada día aparece planificada a esa hora para confirmarla con un toque.</Hint>
    </Sheet>
  );
}

export function OutdatedNotice({ onChanged }: { onChanged: () => void }) {
  const [found, setFound] = useState<Outdated[]>([]);
  const toast = useToast();
  useEffect(() => {
    readOutdated()
      .then(setFound)
      .catch(() => setFound([]));
  }, []);
  if (found.length === 0) return null;
  return (
    <Notice tone="info">
      {found.map((one) => (
        <span key={one.recipe_id} className="macros-outdated">
          {outdatedLabel(one)}.{" "}
          <Button
            variant="plain"
            onClick={() =>
              void recalculateRecipe(one.recipe_id)
                .then((done) => {
                  toast({ message: `Recalculados ${done.items}` });
                  setFound((current) => current.filter((other) => other.recipe_id !== one.recipe_id));
                  onChanged();
                })
                .catch((reason: unknown) => failed(toast, reason, "No se ha podido recalcular"))
            }
          >
            Recalcular
          </Button>
        </span>
      ))}
    </Notice>
  );
}

export function menuLine(menu: Pick<Template, "items" | "daily_at">): string {
  const things = `${menu.items.length} ${menu.items.length === 1 ? "cosa" : "cosas"}`;
  const daily = dailyLabel(menu);
  return daily ? `${things} · ${daily}` : things;
}

export function MenuSettings() {
  const found = useResource("menus", readTemplates);
  const [open, setOpen] = useState<Template | null>(null);
  const menus = found.data ?? [];
  return (
    <Card title="Menús">
      {menus.length === 0 ? (
        <Hint>
          {found.error
            ? found.error.message
            : "Aún no hay menús. Guarda uno desde el menú de una comida, o díselo a Claude: «guarda el desayuno como menú»."}
        </Hint>
      ) : (
        <List>
          {menus.map((menu) => (
            <ListRow key={menu.id} title={menu.name} subtitle={menuLine(menu)} accessory="edit" onClick={() => setOpen(menu)} />
          ))}
        </List>
      )}
      {open && (
        <MenuSheet
          menu={open}
          onClose={() => setOpen(null)}
          onChanged={() => {
            setOpen(null);
            void found.refresh();
          }}
        />
      )}
    </Card>
  );
}

function MenuSheet({ menu, onClose, onChanged }: { menu: Template; onClose: () => void; onChanged: () => void }) {
  const before = menu.daily_at?.slice(0, 5) ?? "";
  const [at, setAt] = useState(before);
  const [step, setStep] = useState<"main" | "time" | "delete">("main");
  return (
    <Sheet title={menu.name} onClose={onClose}>
      <Hint>{menuLine(menu)}</Hint>
      {step === "main" && (
        <>
          <TextField label="Cada día a las (opcional)" type="time" value={at} onChange={setAt} />
          <Hint>Con hora, cada día aparece planificado a esa hora para confirmarlo con un toque.</Hint>
          <div className="macros-item-actions">
            <Button variant="tinted" icon="clock" disabled={at === before} onClick={() => setStep("time")}>
              Guardar la hora
            </Button>
            <Button variant="destructive" icon="trash" onClick={() => setStep("delete")}>
              Borrar
            </Button>
          </div>
        </>
      )}
      {step === "time" && (
        <ConfirmPanel
          title="¿Cambiar la hora del menú?"
          changes={[{ label: "Cada día", from: before || "nunca", to: at || "nunca" }]}
          action="Guardar"
          onCancel={() => setStep("main")}
          onConfirm={() => saveTemplate({ name: menu.name, items: menu.items, said: menu.said, daily_at: at || null }).then(onChanged)}
        />
      )}
      {step === "delete" && (
        <ConfirmPanel
          title={`¿Borrar «${menu.name}»?`}
          detail="Lo ya apuntado con él se queda. No se puede deshacer."
          action="Borrar menú"
          destructive
          onCancel={() => setStep("main")}
          onConfirm={() => removeTemplate(menu.id).then(onChanged)}
        />
      )}
    </Sheet>
  );
}
