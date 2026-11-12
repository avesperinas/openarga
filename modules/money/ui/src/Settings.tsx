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
} from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import { APP, ScreenHeader } from "./Header";
import { NewProductSheet, ProductSheet } from "./Products";
import { RulesScreen } from "./Rules";
import { type AccountRef, type Category, Refused, type State, api } from "./api";
import { money, shortDay } from "./format";

type View = "main" | "accounts" | "categories" | "rules";

export function SettingsScreen({ state, onChanged }: { state: State; onChanged: () => void }) {
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
        <Notice tone="warning" title={`${state.unmapped.length} cuentas de tus bancos sin asignar`}>
          {state.unmapped.map((u) => `${u.bank} ${u.name}${u.iban_tail ? ` ···${u.iban_tail}` : ""}`).join(" · ")}. Sus
          movimientos no se ven hasta que sean un producto: créalo, o asígnala a uno, en Cuentas y productos.
        </Notice>
      )}

      {state.configured && (
        <Section title="Tus datos">
          <List>
            <ListRow
              title="Cuentas y productos"
              icon="wallet"
              hue={4}
              detail={off ? `${off} no ${off === 1 ? "cuadra" : "cuadran"}` : undefined}
              tone={off ? "warning" : undefined}
              value={String(state.accounts.length)}
              accessory="chevron-right"
              onClick={() => open("accounts")}
            />
            <ListRow
              title="Categorías"
              icon="list"
              hue={6}
              value={String(state.categories.length)}
              accessory="chevron-right"
              onClick={() => open("categories")}
            />
            <ListRow
              title="Reglas"
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
  if (h.ok || h.gap === null) return "Cuadra con el banco";
  const amount = money(Math.abs(h.gap), false);
  return h.gap > 0
    ? `El saldo del banco tiene ${amount} menos que sus movimientos: falta por llegar un cargo. Si es reciente, se arregla solo cuando el banco lo publique.`
    : `El saldo del banco tiene ${amount} más que sus movimientos: falta por llegar un ingreso. Si es reciente, se arregla solo cuando el banco lo publique.`;
}

function accountLine(a: AccountRef): string {
  const parts = [a.institution, a.type_label];
  if (a.shared) parts.push("común");
  if (a.ownership < 1) parts.push(`${Math.round(a.ownership * 100)} % tuyo`);
  if (a.role === "emergency_fund") parts.push("fondo de contingencia");
  return parts.join(" · ");
}

function AccountsScreen({ state, onBack, onChanged }: { state: State; onBack: () => void; onChanged: () => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const health = new Map(state.health.map((h) => [h.account, h]));
  const groups = [...new Set(state.accounts.map((a) => a.group))];
  const warning = editing ? health.get(editing) : undefined;

  return (
    <Screen label="Cuentas y productos">
      <ScreenHeader title="Cuentas y productos" back={{ label: "Ajustes", onClick: onBack }} />
      <Section action={{ label: "+ Nuevo producto", onClick: () => setAdding(true) }}>
        <Hint>
          Toca uno para ver de dónde salen sus datos, cómo se valora y en qué fondos está, y cambiar lo que quieras.
        </Hint>
      </Section>
      {groups.map((group) => (
        <Section key={group} title={group}>
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
                    detail={h && !h.ok ? "No cuadra" : undefined}
                    tone={h && !h.ok ? "warning" : undefined}
                    accessory="chevron-right"
                    onClick={() => setEditing(a.key)}
                  />
                );
              })}
          </List>
        </Section>
      ))}
      <Hint>«No cuadra» compara el saldo que da el banco con sus movimientos de los últimos dos meses.</Hint>
      {warning && !warning.ok && (
        <Notice tone="warning" title="No cuadra con el banco">
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
  { nature: "expense", ownership: "individual", title: "Gasto tuyo" },
  { nature: "expense", ownership: "shared", title: "Gasto común" },
  { nature: "income", ownership: "individual", title: "Ingresos" },
];

const SPLIT: Record<string, string> = { fifty_fifty: "A medias", proportional: "Según ingresos" };

function categoryLine(c: Category): string | undefined {
  const parts: string[] = [];
  if (c.split) parts.push(SPLIT[c.split] ?? c.split);
  if (c.nature === "expense") {
    if (c.not_living) parts.push("no es gasto de vida");
    else if (c.not_basic) parts.push("no es básico");
  }
  return parts.length ? parts.join(" · ") : undefined;
}

type Draft = { id: string | null; nature: Category["nature"]; ownership: Category["ownership"]; name: string; split: Category["split"]; not_living: boolean; not_basic: boolean };

function CategoriesScreen({ state, onBack, onChanged }: { state: State; onBack: () => void; onChanged: () => void }) {
  const [editing, setEditing] = useState<Draft | null>(null);
  const groups = GROUPS.filter((g) => g.ownership === "individual" || g.nature === "expense");
  const others = state.categories.filter((c) => !GROUPS.some((g) => g.nature === c.nature && g.ownership === c.ownership));

  return (
    <Screen label="Categorías">
      <ScreenHeader title="Categorías" back={{ label: "Ajustes", onClick: onBack }} />
      {groups.map((g) => {
        const cats = state.categories.filter((c) => c.nature === g.nature && c.ownership === g.ownership);
        return (
          <Section
            key={g.title}
            title={g.title}
            count={cats.length}
            action={{
              label: "+ Añadir",
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
        <Section title="Otras">
          <List>
            {others.map((c) => (
              <ListRow key={c.id} title={c.name} subtitle={categoryLine(c)} accessory="chevron-right" onClick={() => setEditing({ ...c })} />
            ))}
          </List>
        </Section>
      )}
      <Hint>Lo que no es básico sale del gasto básico (y del objetivo del fondo); lo que no es de vida, de los dos gastos.</Hint>
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
      toast({ message: isNew ? "Categoría creada" : "Categoría guardada" });
      onSaved();
    } catch (e) {
      setProblem(e instanceof Refused ? capital(e.message) : "No se ha podido guardar.");
      setSaving(false);
    }
  };

  return (
    <Sheet
      title={isNew ? "Nueva categoría" : initial.name}
      onClose={onClose}
      action={{ label: isNew ? "Crear" : "Guardar", onClick: save, disabled: !name || !changed || saving }}
    >
      {problem && <Hint tone="warning">{problem}</Hint>}
      <TextField
        label="Nombre"
        value={draft.name}
        onChange={(v) => set({ name: v })}
        autoFocus={isNew}
        hint={!isNew && name !== initial.name ? "También se renombra en el histórico." : undefined}
      />
      {draft.ownership === "shared" && (
        <SegmentedControl<"fifty_fifty" | "proportional">
          label="Cómo se reparte"
          value={draft.split ?? "proportional"}
          onChange={(v) => set({ split: v })}
          options={[
            { value: "fifty_fifty", label: "A medias" },
            { value: "proportional", label: "Según ingresos" },
          ]}
        />
      )}
      {draft.nature === "expense" && (
        <>
          <div className="money-switch-row">
            <span className="money-switch-text">
              <span>Gasto de vida</span>
              <span className="money-switch-hint">Apágalo para lo que no es vivir (Trabajo): sale del gasto mensual.</span>
            </span>
            <Switch label="Gasto de vida" checked={!draft.not_living} onChange={(on) => set({ not_living: !on })} />
          </div>
          <div className="money-switch-row">
            <span className="money-switch-text">
              <span>Gasto básico</span>
              <span className="money-switch-hint">Apágalo para lo prescindible (Ocio, Viajes): sale del gasto básico.</span>
            </span>
            <Switch label="Gasto básico" checked={!draft.not_basic} onChange={(on) => set({ not_basic: !on })} />
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
  const nameOf = (key: string) => state.accounts.find((a) => a.key === key)?.name ?? "Ninguna";

  return (
    <Section title="Fondo de contingencia">
      <SelectField<string>
        label="Cuenta"
        value={fund}
        onChange={setFund}
        options={[{ value: "", label: "Ninguna" }, ...state.accounts.map((a) => ({ value: a.key, label: `${a.name} · ${a.institution}` }))]}
      />
      <Stepper label="Meses de gasto básico" value={months} step={1} min={1} max={24} inputMode="numeric" unit="meses" onChange={setMonths} />
      <Hint>El objetivo del fondo es tu gasto básico mensual por estos meses. Esa cuenta no cuenta como cash.</Hint>
      {changed && (
        <Button variant="tinted" onClick={() => setConfirm(true)}>
          Guardar
        </Button>
      )}
      {confirm && months !== null && (
        <ConfirmChange
          title="¿Guardar el fondo de contingencia?"
          changes={[
            ...(fund !== fundNow ? [{ label: "Cuenta", from: nameOf(fundNow), to: nameOf(fund) }] : []),
            ...(months !== savedMonths ? [{ label: "Objetivo", from: `${savedMonths} meses`, to: `${months} meses` }] : []),
          ]}
          detail="Cambia el objetivo del fondo y qué cuenta cuenta como cash."
          action="Guardar"
          onCancel={() => setConfirm(false)}
          onConfirm={async () => {
            await api.settings(months, fund || null);
            setSavedMonths(months);
            setConfirm(false);
            toast({ message: "Fondo de contingencia guardado" });
            onChanged();
          }}
        />
      )}
    </Section>
  );
}

function Backup({ state, onChanged }: { state: State; onChanged: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<{ name: string; bundle: unknown } | null>(null);
  const [message, setMessage] = useState<{ tone: "positive" | "negative"; text: string } | null>(null);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    try {
      setPending({ name: file.name, bundle: JSON.parse(await file.text()) });
    } catch {
      setMessage({ tone: "negative", text: "Ese fichero no es una configuración de Money." });
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
    <Section title="Copia de la configuración">
      {message && <Notice tone={message.tone} title={message.tone === "positive" ? "Hecho" : "No se ha podido"}>{message.text}</Notice>}
      <List>
        <ListRow title="Reglas" value={String(state.rules)} />
        <ListRow title="El libro empieza" value={state.cutoff ? shortDay(state.cutoff) : "Sin corte"} detail={state.cutoff ? "antes, el histórico" : undefined} />
      </List>
      <div className="money-actions">
        <Button icon="external" variant="tinted" onClick={download} disabled={!state.configured}>
          Descargar copia
        </Button>
        <Button icon="file" variant="plain" onClick={() => input.current?.click()}>
          Importar configuración
        </Button>
      </div>
      <input ref={input} type="file" accept="application/json,.json" hidden onChange={(e) => pick(e.target.files?.[0])} />
      <Hint>Cuentas, categorías, reglas, etiquetas, ingresos declarados y el histórico, en un fichero. Importar sustituye lo que haya.</Hint>
      {pending && (
        <ConfirmDelete
          title="¿Sustituir la configuración?"
          subject={pending.name}
          consequence="Las cuentas, categorías, reglas, etiquetas, gastos apuntados e ingresos de ahora se cambian por los del fichero. Descarga antes una copia si quieres poder volver."
          action="Sustituir configuración"
          onCancel={() => setPending(null)}
          onConfirm={async () => {
            try {
              const counts = await api.importBundle(pending.bundle);
              setMessage({
                tone: "positive",
                text: `${counts.accounts} cuentas, ${counts.categories} categorías, ${counts.rules} reglas y ${counts.labels} etiquetas.`,
              });
              onChanged();
            } catch (e) {
              setMessage({ tone: "negative", text: e instanceof Refused ? e.message : "No se ha podido importar." });
            }
            setPending(null);
          }}
        />
      )}
    </Section>
  );
}
