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
  useT,
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
  const t = useT();
  const { list, reload } = useCategories();
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const [sharing, setSharing] = useState<Category | null>(null);

  useEffect(reload, [reload]);

  const current = editing && editing !== "new" ? list.find((one) => one.id === editing.id) : undefined;

  return (
    <Screen>
      <ScreenHeader title={t("settings.categories")} />
      {list.length === 0 ? (
        <EmptyState
          icon="layers"
          hue={3}
          title={t("categories.empty")}
          action={{ label: t("categories.create_one"), icon: "plus", onClick: () => setEditing("new") }}
        >
          <p>{t("categories.empty_detail")}</p>
        </EmptyState>
      ) : (
        <List>
          {list.map((one) => (
            <ListRow
              key={one.id}
              title={one.name}
              subtitle={
                [
                  count(t, "categories.pending", one.pending),
                  one.goals ? count(t, "categories.goals", one.goals) : null,
                  one.space_id ? t("task.shared") : null,
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
      <CreateButton label={t("home.category")} onClick={() => setEditing("new")} />

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
  const t = useT();
  return (
    <div className="goals-hues" role="radiogroup" aria-label={t("categories.colour")}>
      {HUES.map((hue) => (
        <button
          key={hue}
          type="button"
          role="radio"
          className="goals-hue"
          aria-checked={hue === value}
          aria-label={t(`hue.${hue}`)}
          onClick={() => onChange(hue)}
        >
          <span className="list-row-dot" data-hue={hue} aria-hidden="true" />
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
  const t = useT();
  const free = HUES.find((hue) => !all.some((one) => one.hue === hue)) ?? 1;
  const [name, setName] = useState(category?.name ?? "");
  const [hue, setHue] = useState(category?.hue ?? free);
  const [deleting, setDeleting] = useState(false);
  const { busy, error, run } = useBusy();

  const save = () =>
    void run(async () => {
      if (category) await updateCategory(category.id, { name: name.trim(), hue });
      else await createCategory(name.trim(), hue);
      onChanged();
    }, t("sheet.save_failed"));

  const move = (step: -1 | 1) =>
    void run(async () => {
      const ids = all.map((one) => one.id);
      const at = ids.indexOf(category!.id);
      const to = at + step;
      if (to < 0 || to >= ids.length) return;
      [ids[at], ids[to]] = [ids[to]!, ids[at]!];
      await orderCategories(ids);
      onChanged(false);
    }, t("categories.move_failed"));

  if (deleting && category) {
    return (
      <ConfirmDelete
        title={t("categories.delete_question")}
        subject={category.name}
        consequence={
          category.pending > 0
            ? t("categories.delete_pending", {
                pending: count(t, "categories.pending", category.pending),
                goals: category.goals ? t("categories.goals_stay") : "",
              })
            : t("categories.delete_done", { goals: category.goals ? t("categories.goals_stay") : "" })
        }
        action={t("categories.delete")}
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
      title={category ? category.name : t("categories.new")}
      onClose={onClose}
      action={{ label: category ? t("sheet.save") : t("categories.create"), onClick: save, disabled: busy || !name.trim() }}
    >
      <div className="goals-form">
        <TextField label={t("categories.name")} value={name} placeholder={t("categories.name_placeholder")} autoFocus={!category} onChange={setName} />
        <HuePicker value={hue} onChange={setHue} />
        {category && (
          <>
            <div className="goals-row-actions">
              <Button icon="chevron-up" disabled={busy || position <= 0} onClick={() => move(-1)}>
                {t("categories.up")}
              </Button>
              <Button icon="chevron-down" disabled={busy || position >= all.length - 1} onClick={() => move(1)}>
                {t("categories.down")}
              </Button>
              <Button icon="people" onClick={onShare}>
                {category.space_id ? t("categories.shared") : t("categories.share")}
              </Button>
            </div>
            <Button variant="destructive" icon="trash" block onClick={() => setDeleting(true)}>
              {t("categories.delete")}
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
  const t = useT();
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
    }, t("categories.share_failed"));

  return (
    <Sheet title={t("categories.share_title", { name: category.name })} onClose={onClose}>
      {mode === "pick" && (
        <div className="goals-form">
          <Hint>{t("categories.share_hint")}</Hint>
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
                  <strong>{t("categories.only_you")}</strong>
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
                      {space.members === 1 ? t("categories.only_you_yet") : t("categories.people", { count: space.members })}
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
                      }, t("categories.invite_failed"))
                    }
                  >
                    {t("categories.invite")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {invite && (
            <div className="goals-invite">
              <span>{t("categories.invite_code", { space: invite.space })}</span>
              <strong className="goals-code">{invite.code}</strong>
            </div>
          )}
          <div className="goals-row-actions">
            <Button icon="plus" onClick={() => setMode("create")}>
              {t("categories.new_space")}
            </Button>
            <Button onClick={() => setMode("join")}>{t("categories.have_code")}</Button>
          </div>
        </div>
      )}
      {mode === "create" && (
        <div className="goals-form">
          <TextField label={t("categories.space_name")} value={name} placeholder={t("categories.space_placeholder")} autoFocus onChange={setName} />
          <Button
            variant="primary"
            block
            disabled={busy || !name.trim()}
            onClick={() =>
              void run(async () => {
                await createSpace(name.trim());
                await load();
                setMode("pick");
              }, t("categories.create_failed"))
            }
          >
            {t("categories.create")}
          </Button>
        </div>
      )}
      {mode === "join" && (
        <div className="goals-form">
          <TextField label={t("categories.code")} value={code} placeholder="ABCD-EFGH-JKMN" autoFocus onChange={setCode} />
          <Button
            variant="primary"
            block
            disabled={busy || code.replace(/[^a-z0-9]/gi, "").length < 12}
            onClick={() =>
              void run(async () => {
                await joinSpace(code.trim());
                await load();
                setMode("pick");
              }, t("categories.bad_code"))
            }
          >
            {t("categories.join")}
          </Button>
        </div>
      )}
      <Problem error={error} />
    </Sheet>
  );
}
