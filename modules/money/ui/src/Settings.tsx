import {
  AppSettings,
  Button,
  ConfirmChange,
  ConfirmDelete,
  Hint,
  List,
  ListRow,
  Notice,
  Screen,
  Section,
  SegmentedControl,
  SelectField,
  Sheet,
  Stepper,
  Switch,
  TextField,
  useToast,
  useT,
} from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import { APP, ScreenHeader } from "./Header";
import { NewProductSheet, ProductSheet } from "./Products";
import { RulesScreen } from "./Rules";
import { type AccountRef, type Category, Refused, type State, api } from "./api";
import { groupName, money, percentText, say, shortDay, typeName } from "./format";

type View = "main" | "accounts" | "categories" | "rules";

export function SettingsScreen({ state, onChanged }: { state: State; onChanged: () => void }) {
  const t = useT();
  const [view, setView] = useState<View>("main");
  const back = () => {
    setView("main");
    window.scrollTo(0, 0);
  };
  const open = (next: View) => {
    setView(next);
    window.scrollTo(0, 0);
  };

  if (view === "accounts") return <AccountsScreen state={state} onBack={back} onChanged={onChanged} />;
  if (view === "categories") return <CategoriesScreen state={state} onBack={back} onChanged={onChanged} />;
  if (view === "rules") return <RulesScreen onBack={back} onChanged={onChanged} />;

  const off = state.health.filter((h) => !h.ok).length;
  return (
    <AppSettings app={APP}>
      {state.unmapped.length > 0 && (
        <Notice tone="warning" title={t("settings.unmapped", { count: state.unmapped.length })}>
          {t("settings.unmapped_body", { accounts: state.unmapped.map((u) => `${u.bank} ${u.name}${u.iban_tail ? ` ···${u.iban_tail}` : ""}`).join(" · ") })}
        </Notice>
      )}

      {state.configured && (
        <Section title={t("settings.your_data")}>
          <List>
            <ListRow
              title={t("settings.accounts")}
              icon="wallet"
              hue={4}
              detail={off ? (off === 1 ? t("settings.off_one") : t("settings.off_other", { count: off })) : undefined}
              tone={off ? "warning" : undefined}
              value={String(state.accounts.length)}
              accessory="chevron-right"
              onClick={() => open("accounts")}
            />
            <ListRow
              title={t("settings.categories")}
              icon="list"
              hue={6}
              value={String(state.categories.length)}
              accessory="chevron-right"
              onClick={() => open("categories")}
            />
            <ListRow
              title={t("settings.rules")}
              icon="list"
              hue={2}
              value={String(state.rules)}
              accessory="chevron-right"
              onClick={() => open("rules")}
            />
          </List>
        </Section>
      )}

      {state.configured && <EmergencyFund state={state} onChanged={onChanged} />}

      <Backup state={state} onChanged={onChanged} />
    </AppSettings>
  );
}

type Health = State["health"][number];

function healthText(h: Health): string {
  if (h.ok || h.gap === null) return say("health.ok");
  const amount = money(Math.abs(h.gap), false);
  return h.gap > 0 ? say("health.less", { amount }) : say("health.more", { amount });
}

function accountLine(a: AccountRef): string {
  const parts = [a.institution, typeName(a.type, a.type_label)];
  if (a.shared) parts.push(say("account.shared"));
  if (a.ownership < 1) parts.push(say("account.yours", { percent: percentText(Math.round(a.ownership * 100) / 100) }));
  if (a.role === "emergency_fund") parts.push(say("account.emergency"));
  return parts.join(" · ");
}

function AccountsScreen({ state, onBack, onChanged }: { state: State; onBack: () => void; onChanged: () => void }) {
  const t = useT();
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const health = new Map(state.health.map((h) => [h.account, h]));
  const groups = [...new Set(state.accounts.map((a) => a.group))];
  const warning = editing ? health.get(editing) : undefined;

  return (
    <Screen label={t("settings.accounts")}>
      <ScreenHeader title={t("settings.accounts")} back={{ label: t("tab.settings"), onClick: onBack }} />
      <Section action={{ label: t("settings.new_product"), onClick: () => setAdding(true) }}>
        <Hint>
          {t("settings.accounts_hint")}
        </Hint>
      </Section>
      {groups.map((group) => (
        <Section key={group} title={groupName(group)}>
          <List>
            {state.accounts
              .filter((a) => a.group === group)
              .map((a) => {
                const h = health.get(a.key);
                return (
                  <ListRow
                    key={a.key}
                    title={a.name}
                    subtitle={accountLine(a)}
                    detail={h && !h.ok ? t("settings.off") : undefined}
                    tone={h && !h.ok ? "warning" : undefined}
                    accessory="chevron-right"
                    onClick={() => setEditing(a.key)}
                  />
                );
              })}
          </List>
        </Section>
      ))}
      <Hint>{t("settings.off_hint")}</Hint>
      {warning && !warning.ok && (
        <Notice tone="warning" title={t("settings.off_title")}>
          {healthText(warning)}
        </Notice>
      )}
      {editing && <ProductSheet productKey={editing} state={state} onClose={() => setEditing(null)} onChanged={onChanged} />}
      {adding && (
        <NewProductSheet
          state={state}
          onClose={() => setAdding(false)}
          onCreated={(key) => {
            setAdding(false);
            onChanged();
            setEditing(key);
          }}
        />
      )}
    </Screen>
  );
}

type Group = { nature: Category["nature"]; ownership: Category["ownership"]; title: string };

const GROUPS: Group[] = [
  { nature: "expense", ownership: "individual", title: "group.expense_individual" },
  { nature: "expense", ownership: "shared", title: "group.expense_shared" },
  { nature: "income", ownership: "individual", title: "group.income_individual" },
];

const SPLITS = new Set(["fifty_fifty", "proportional"]);

function categoryLine(c: Category): string | undefined {
  const parts: string[] = [];
  if (c.split) parts.push(SPLITS.has(c.split) ? say(`split.${c.split}`) : c.split);
  if (c.nature === "expense") {
    if (c.not_living) parts.push(say("category.not_living"));
    else if (c.not_basic) parts.push(say("category.not_basic"));
  }
  return parts.length ? parts.join(" · ") : undefined;
}

type Draft = { id: string | null; nature: Category["nature"]; ownership: Category["ownership"]; name: string; split: Category["split"]; not_living: boolean; not_basic: boolean };

function CategoriesScreen({ state, onBack, onChanged }: { state: State; onBack: () => void; onChanged: () => void }) {
  const t = useT();
  const [editing, setEditing] = useState<Draft | null>(null);
  const groups = GROUPS.filter((g) => g.ownership === "individual" || g.nature === "expense");
  const others = state.categories.filter((c) => !GROUPS.some((g) => g.nature === c.nature && g.ownership === c.ownership));

  return (
    <Screen label={t("settings.categories")}>
      <ScreenHeader title={t("settings.categories")} back={{ label: t("tab.settings"), onClick: onBack }} />
      {groups.map((g) => {
        const cats = state.categories.filter((c) => c.nature === g.nature && c.ownership === g.ownership);
        return (
          <Section
            key={g.title}
            title={t(g.title)}
            count={cats.length}
            action={{
              label: t("settings.add"),
              onClick: () =>
                setEditing({
                  id: null,
                  nature: g.nature,
                  ownership: g.ownership,
                  name: "",
                  split: g.ownership === "shared" ? "proportional" : null,
                  not_living: false,
                  not_basic: false,
                }),
            }}
          >
            <List>
              {cats.map((c) => (
                <ListRow key={c.id} title={c.name} subtitle={categoryLine(c)} accessory="chevron-right" onClick={() => setEditing({ ...c })} />
              ))}
            </List>
          </Section>
        );
      })}
      {others.length > 0 && (
        <Section title={t("settings.others")}>
          <List>
            {others.map((c) => (
              <ListRow key={c.id} title={c.name} subtitle={categoryLine(c)} accessory="chevron-right" onClick={() => setEditing({ ...c })} />
            ))}
          </List>
        </Section>
      )}
      <Hint>{t("settings.categories_hint")}</Hint>
      {editing && (
        <CategorySheet
          draft={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
    </Screen>
  );
}

function CategorySheet({ draft: initial, onClose, onSaved }: { draft: Draft; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const toast = useToast();
  const [draft, setDraft] = useState(initial);
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const isNew = draft.id === null;
  const name = draft.name.trim();
  const changed = isNew || JSON.stringify({ ...draft, name }) !== JSON.stringify(initial);
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });

  const save = async () => {
    if (!name) return;
    setSaving(true);
    const body = { name, split: draft.split, not_living: draft.not_living, not_basic: draft.not_basic };
    try {
      if (draft.id) await api.saveCategory(draft.id, body);
      else await api.addCategory({ ...body, nature: draft.nature, ownership: draft.ownership });
      toast({ message: isNew ? t("category.created") : t("category.saved") });
      onSaved();
    } catch (e) {
      setProblem(e instanceof Refused ? capital(e.message) : t("common.save_failed"));
      setSaving(false);
    }
  };

  return (
    <Sheet
      title={isNew ? t("category.new") : initial.name}
      onClose={onClose}
      action={{ label: isNew ? t("category.create") : t("common.save"), onClick: save, disabled: !name || !changed || saving }}
    >
      {problem && <Hint tone="warning">{problem}</Hint>}
      <TextField
        label={t("category.name")}
        value={draft.name}
        onChange={(v) => set({ name: v })}
        autoFocus={isNew}
        hint={!isNew && name !== initial.name ? t("category.renamed") : undefined}
      />
      {draft.ownership === "shared" && (
        <SegmentedControl<"fifty_fifty" | "proportional">
          label={t("category.split")}
          value={draft.split ?? "proportional"}
          onChange={(v) => set({ split: v })}
          options={[
            { value: "fifty_fifty", label: t("split.fifty_fifty") },
            { value: "proportional", label: t("split.proportional") },
          ]}
        />
      )}
      {draft.nature === "expense" && (
        <>
          <div className="money-switch-row">
            <span className="money-switch-text">
              <span>{t("category.living")}</span>
              <span className="money-switch-hint">{t("category.living_hint")}</span>
            </span>
            <Switch label={t("category.living")} checked={!draft.not_living} onChange={(on) => set({ not_living: !on })} />
          </div>
          <div className="money-switch-row">
            <span className="money-switch-text">
              <span>{t("category.basic")}</span>
              <span className="money-switch-hint">{t("category.basic_hint")}</span>
            </span>
            <Switch label={t("category.basic")} checked={!draft.not_basic} onChange={(on) => set({ not_basic: !on })} />
          </div>
        </>
      )}
    </Sheet>
  );
}

function capital(text: string): string {
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}.`;
}

function EmergencyFund({ state, onChanged }: { state: State; onChanged: () => void }) {
  const t = useT();
  const toast = useToast();
  const fundNow = state.accounts.find((a) => a.role === "emergency_fund")?.key ?? "";
  const [months, setMonths] = useState<number | null>(null);
  const [savedMonths, setSavedMonths] = useState<number | null>(null);
  const [fund, setFund] = useState(fundNow);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    api.summary().then((s) => {
      setMonths(s.emergency_months);
      setSavedMonths(s.emergency_months);
    }, () => undefined);
  }, []);
  const changed = months !== null && (months !== savedMonths || fund !== fundNow);
  const nameOf = (key: string) => state.accounts.find((a) => a.key === key)?.name ?? t("emergency.none");

  return (
    <Section title={t("emergency.title")}>
      <SelectField<string>
        label={t("emergency.account")}
        value={fund}
        onChange={setFund}
        options={[{ value: "", label: t("emergency.none") }, ...state.accounts.map((a) => ({ value: a.key, label: `${a.name} · ${a.institution}` }))]}
      />
      <Stepper label={t("emergency.months")} value={months} step={1} min={1} max={24} inputMode="numeric" unit={t("emergency.unit")} onChange={setMonths} />
      <Hint>{t("emergency.hint")}</Hint>
      {changed && (
        <Button variant="tinted" onClick={() => setConfirm(true)}>
          {t("common.save")}
        </Button>
      )}
      {confirm && months !== null && (
        <ConfirmChange
          title={t("emergency.confirm")}
          changes={[
            ...(fund !== fundNow ? [{ label: t("emergency.account"), from: nameOf(fundNow), to: nameOf(fund) }] : []),
            ...(months !== savedMonths ? [{ label: t("emergency.target"), from: t("emergency.months_value", { count: savedMonths ?? 0 }), to: t("emergency.months_value", { count: months }) }] : []),
          ]}
          detail={t("emergency.detail")}
          action={t("common.save")}
          onCancel={() => setConfirm(false)}
          onConfirm={async () => {
            await api.settings(months, fund || null);
            setSavedMonths(months);
            setConfirm(false);
            toast({ message: t("emergency.saved") });
            onChanged();
          }}
        />
      )}
    </Section>
  );
}

function Backup({ state, onChanged }: { state: State; onChanged: () => void }) {
  const t = useT();
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<{ name: string; bundle: unknown } | null>(null);
  const [message, setMessage] = useState<{ tone: "positive" | "negative"; text: string } | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    try {
      setPending({ name: file.name, bundle: JSON.parse(await file.text()) });
    } catch {
      setMessage({ tone: "negative", text: t("backup.not_config") });
    }
  };

  const download = async () => {
    const bundle = await api.exportBundle();
    const blob = new Blob([JSON.stringify(bundle, null, 1)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `money-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <Section title={t("backup.title")}>
      {message && <Notice tone={message.tone} title={message.tone === "positive" ? t("backup.done") : t("backup.failed")}>{message.text}</Notice>}
      <List>
        <ListRow title={t("backup.rules")} value={String(state.rules)} />
        <ListRow title={t("backup.starts")} value={state.cutoff ? shortDay(state.cutoff) : t("backup.no_cutoff")} detail={state.cutoff ? t("backup.before") : undefined} />
      </List>
      <div className="money-actions">
        <Button icon="external" variant="tinted" onClick={download} disabled={!state.configured}>
          {t("backup.download")}
        </Button>
        <Button icon="file" variant="plain" onClick={() => input.current?.click()}>
          {t("backup.import")}
        </Button>
      </div>
      <input ref={input} type="file" accept="application/json,.json" hidden onChange={(e) => pick(e.target.files?.[0])} />
      <Hint>{t("backup.hint")}</Hint>
      {pending && (
        <ConfirmDelete
          title={t("backup.replace_q")}
          subject={pending.name}
          consequence={t("backup.replace_consequence")}
          action={t("backup.replace")}
          onCancel={() => setPending(null)}
          onConfirm={async () => {
            try {
              const counts = await api.importBundle(pending.bundle);
              setMessage({
                tone: "positive",
                text: t("backup.imported", { accounts: counts.accounts ?? 0, categories: counts.categories ?? 0, rules: counts.rules ?? 0, labels: counts.labels ?? 0 }),
              });
              onChanged();
            } catch (e) {
              setMessage({ tone: "negative", text: e instanceof Refused ? e.message : t("backup.import_failed") });
            }
            setPending(null);
          }}
        />
      )}
    </Section>
  );
}
