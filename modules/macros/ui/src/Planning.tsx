import { useResource } from "@openarga/app";
import { Button, Card, ConfirmPanel, Hint, List, ListRow, Notice, Sheet, TextField, type Translate, useT, useToast } from "@openarga/ui";
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
import { plural } from "./words";

export function dailyLabel(template: Pick<Template, "daily_at">, t: Translate): string | undefined {
  return template.daily_at ? t("menu.daily_at", { at: template.daily_at.slice(0, 5) }) : undefined;
}

export function outdatedLabel(one: Outdated, t: Translate): string {
  return `${one.name}: ${plural(t, "outdated.records", one.items)}`;
}

function failed(toast: ReturnType<typeof useToast>, reason: unknown, fallback: string) {
  toast({ message: reason instanceof Error ? reason.message : fallback, tone: "error" });
}

export function SaveTemplateSheet({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const t = useT();
  const [name, setName] = useState(entry.said ?? entry.items.map((item) => item.name).join(" + "));
  const [at, setAt] = useState("");
  const toast = useToast();
  const valid = /^([01]\d|2[0-3]):[0-5]\d$/.test(at.trim());
  const save = () =>
    void templateFromEntry(entry.id, name.trim(), valid ? at.trim() : null)
      .then(() => {
        toast({ message: t("menu.saved") });
        onClose();
      })
      .catch((reason: unknown) => failed(toast, reason, t("common.save_failed")));
  return (
    <Sheet
      title={t("menu.save_as")}
      onClose={onClose}
      action={{ label: t("common.save"), onClick: save, disabled: !name.trim() || (at.trim() !== "" && !valid) }}
    >
      <TextField label={t("common.name")} value={name} onChange={setName} autoFocus />
      <TextField label={t("menu.daily_optional")} type="time" value={at} onChange={setAt} />
      <Hint>{t("menu.daily_hint")}</Hint>
    </Sheet>
  );
}

export function OutdatedNotice({ onChanged }: { onChanged: () => void }) {
  const t = useT();
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
          {outdatedLabel(one, t)}.{" "}
          <Button
            variant="plain"
            onClick={() =>
              void recalculateRecipe(one.recipe_id)
                .then((done) => {
                  toast({ message: t("outdated.done", { count: done.items }) });
                  setFound((current) => current.filter((other) => other.recipe_id !== one.recipe_id));
                  onChanged();
                })
                .catch((reason: unknown) => failed(toast, reason, t("outdated.failed")))
            }
          >
            {t("outdated.recalculate")}
          </Button>
        </span>
      ))}
    </Notice>
  );
}

export function menuLine(menu: Pick<Template, "items" | "daily_at">, t: Translate): string {
  const things = plural(t, "things", menu.items.length);
  const daily = dailyLabel(menu, t);
  return daily ? `${things} · ${daily}` : things;
}

export function MenuSettings() {
  const t = useT();
  const found = useResource("menus", readTemplates);
  const [open, setOpen] = useState<Template | null>(null);
  const menus = found.data ?? [];
  return (
    <Card title={t("menu.menus")}>
      {menus.length === 0 ? (
        <Hint>
          {found.error
            ? found.error.message
            : t("menu.none")}
        </Hint>
      ) : (
        <List>
          {menus.map((menu) => (
            <ListRow key={menu.id} title={menu.name} subtitle={menuLine(menu, t)} accessory="edit" onClick={() => setOpen(menu)} />
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
  const t = useT();
  const before = menu.daily_at?.slice(0, 5) ?? "";
  const [at, setAt] = useState(before);
  const [step, setStep] = useState<"main" | "time" | "delete">("main");
  return (
    <Sheet title={menu.name} onClose={onClose}>
      <Hint>{menuLine(menu, t)}</Hint>
      {step === "main" && (
        <>
          <TextField label={t("menu.daily_optional")} type="time" value={at} onChange={setAt} />
          <Hint>{t("menu.daily_hint")}</Hint>
          <div className="macros-item-actions">
            <Button variant="tinted" icon="clock" disabled={at === before} onClick={() => setStep("time")}>
              {t("menu.save_time")}
            </Button>
            <Button variant="destructive" icon="trash" onClick={() => setStep("delete")}>
              {t("common.delete")}
            </Button>
          </div>
        </>
      )}
      {step === "time" && (
        <ConfirmPanel
          title={t("menu.time_title")}
          changes={[{ label: t("menu.every_day"), from: before || t("menu.never"), to: at || t("menu.never") }]}
          action={t("common.save")}
          onCancel={() => setStep("main")}
          onConfirm={() => saveTemplate({ name: menu.name, items: menu.items, said: menu.said, daily_at: at || null }).then(onChanged)}
        />
      )}
      {step === "delete" && (
        <ConfirmPanel
          title={t("common.delete_named", { name: menu.name })}
          detail={t("menu.delete_detail")}
          action={t("menu.delete")}
          destructive
          onCancel={() => setStep("main")}
          onConfirm={() => removeTemplate(menu.id).then(onChanged)}
        />
      )}
    </Sheet>
  );
}
