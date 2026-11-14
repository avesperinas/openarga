import {
  Button,
  DateField,
  Hint,
  IconButton,
  List,
  ListRow,
  Notice,
  Section,
  SegmentedControl,
  SelectField,
  Sheet,
  Stepper,
  Switch,
  TextField,
  useToast,
  type Translate,
  useT,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { signedPercent } from "./analysisParts";
import { type FundRow, type ProductChange, type ProductDetail, Refused, type State, type TypedFund, api } from "./api";
import { amountText, capital, currencySymbol, isoDay, money, parseAmount, percentText, say, shortDay, typeName } from "./format";

const VALUE_MODES = ["balance", "computed", "snapshot", "manual"];
const valueModes = () => VALUE_MODES.map((value) => ({ value, label: say(`mode.${value}`) }));

function problemOf(e: unknown): string {
  return e instanceof Refused ? capital(e.message) : say("common.save_failed");
}

function fundLine(f: FundRow): string {
  const parts = [f.asset_name];
  if (f.regions.length) parts.push(f.regions.map((r) => `${r.name} ${percentText(Math.round(r.weight) / 100)}`).join(", "));
  if (f.classified === "unknown") parts.push(say("product.unclassified"));
  if (f.classified === "yours") parts.push(say("product.classified_yours"));
  return parts.join(" · ");
}

export function FundListRow({ fund, onClick }: { fund: FundRow; onClick?: () => void }) {
  return (
    <ListRow
      title={fund.name}
      subtitle={fundLine(fund)}
      value={money(fund.value, false)}
      detail={fund.change !== null ? signedPercent(fund.change) : undefined}
      tone={fund.classified === "unknown" ? "warning" : undefined}
      accessory={onClick ? "chevron-right" : undefined}
      onClick={onClick}
    />
  );
}

type Mode = { kind: "detail" } | { kind: "composition" } | { kind: "fund"; fund: FundRow } | { kind: "value" };

export function ProductSheet({
  productKey,
  state,
  onClose,
  onChanged,
}: {
  productKey: string;
  state: State;
  onClose: () => void;
  onChanged: () => void;
}) {
  const t = useT();
  const toast = useToast();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: "detail" });
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    api.product(productKey).then(setProduct, () => setProblem(t("product.open_failed")));
  }, [productKey]);

  const saved = (next: ProductDetail, message: string) => {
    setProduct(next);
    setMode({ kind: "detail" });
    setProblem(null);
    toast({ message });
    onChanged();
  };

  if (!product)
    return (
      <Sheet title={t("product.title")} onClose={onClose}>
        {problem ? <Hint tone="warning">{problem}</Hint> : <Hint>{t("product.loading")}</Hint>}
      </Sheet>
    );

  const back = () => {
    setMode({ kind: "detail" });
    setProblem(null);
  };
  if (mode.kind === "composition")
    return <CompositionEditor product={product} onBack={back} onSaved={(p) => saved(p, t("product.composition_saved"))} />;
  if (mode.kind === "fund")
    return (
      <FundEditor
        fund={mode.fund}
        state={state}
        onBack={back}
        onSaved={async () => saved(await api.product(product.key), t("product.fund_saved"))}
      />
    );
  if (mode.kind === "value")
    return <ValueEditor product={product} onBack={back} onSaved={(p) => saved(p, t("product.value_saved"))} />;
  return (
    <DetailEditor
      product={product}
      state={state}
      onClose={onClose}
      onSaved={(p) => saved(p, t("product.saved"))}
      onMode={setMode}
      onChanged={(p) => {
        setProduct(p);
        onChanged();
      }}
    />
  );
}

function DetailEditor({
  product,
  state,
  onClose,
  onSaved,
  onMode,
  onChanged,
}: {
  product: ProductDetail;
  state: State;
  onClose: () => void;
  onSaved: (p: ProductDetail) => void;
  onMode: (m: Mode) => void;
  onChanged: (p: ProductDetail) => void;
}) {
  const t = useT();
  const [name, setName] = useState(product.name);
  const [type, setType] = useState(product.type);
  const [institution, setInstitution] = useState(product.institution);
  const [share, setShare] = useState<number | null>(Math.round(product.ownership * 100));
  const [shared, setShared] = useState(product.shared);
  const [valueMode, setValueMode] = useState("");
  const [source, setSource] = useState("");
  const [ibans, setIbans] = useState(product.ibans);
  const [iban, setIban] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const change: ProductChange = {};
  if (name.trim() !== product.name) change.name = name.trim();
  if (type !== product.type) change.type = type;
  if (institution.trim() !== product.institution) change.institution = institution.trim();
  if (share !== null && share !== Math.round(product.ownership * 100)) change.ownership = share / 100;
  if (shared !== product.shared) change.shared = shared;
  if (valueMode) change.value = valueMode === "type" ? "" : valueMode;
  if (source) change.source = source;
  if (JSON.stringify(ibans) !== JSON.stringify(product.ibans)) change.ibans = ibans;
  const valid = name.trim().length > 0 && institution.trim().length > 0 && share !== null && share >= 1 && share <= 100;
  const changed = Object.keys(change).length > 0;

  const save = async () => {
    setSaving(true);
    try {
      onSaved(await api.changeProduct(product.key, change));
    } catch (e) {
      setProblem(problemOf(e));
      setSaving(false);
    }
  };

  const removeTyped = async () => {
    if (!product.photo) return;
    try {
      onChanged(await api.removeComposition(product.key, product.photo.on));
    } catch (e) {
      setProblem(problemOf(e));
    }
  };

  const invested = product.asset_class === "investment";
  const since = product.value_since ? t("product.since", { day: shortDay(product.value_since) }) : "";

  return (
    <Sheet title={product.name} onClose={onClose} action={{ label: t("common.save"), onClick: save, disabled: !valid || !changed || saving }}>
      {problem && <Hint tone="warning">{problem}</Hint>}

      <Section title={t("product.its_value")}>
        <List>
          <ListRow
            title={t("product.worth")}
            value={product.value === null ? t("product.no_value") : money(product.value, false)}
            detail={product.estimated ? t("product.estimated", { day: shortDay(product.estimated) }) : undefined}
          />
          {product.contributed !== null && <ListRow title={t("product.contributed")} value={money(product.contributed, false)} />}
        </List>
        <Hint>
          {t("product.how", { how: product.value_how.charAt(0).toLowerCase() + product.value_how.slice(1), since })}
        </Hint>
        <SelectField<string>
          label={t("product.valued")}
          value={valueMode}
          onChange={setValueMode}
          options={[{ value: "", label: t("product.as_now", { mode: modeLabel(product.value_mode) }) }, { value: "type", label: t("product.by_type") }, ...valueModes()]}
        />
        <Button variant="tinted" size="small" onClick={() => onMode({ kind: "value" })}>
          {t("product.record_value")}
        </Button>
      </Section>

      {invested && (
        <Section title={product.photo ? t("product.funds_on", { day: shortDay(product.photo.on) }) : t("product.funds")}>
          {product.photo ? (
            <List>
              {product.photo.funds.map((f) => (
                <FundListRow key={f.symbol} fund={f} onClick={() => onMode({ kind: "fund", fund: f })} />
              ))}
            </List>
          ) : (
            <Hint>{t("product.no_funds")}</Hint>
          )}
          {product.photo?.typed && <Hint>{t("product.typed")}</Hint>}
          {product.photo && <Hint>{t("product.tap_fund")}</Hint>}
          <Button variant="tinted" size="small" onClick={() => onMode({ kind: "composition" })}>
            {t("product.record_composition")}
          </Button>
          {product.photo?.typed && (
            <Button variant="plain" size="small" onClick={removeTyped}>
              {t("product.remove_typed")}
            </Button>
          )}
        </Section>
      )}

      <Section title={t("product.what")}>
        <TextField label={t("product.name")} value={name} onChange={setName} invalid={!name.trim()} />
        <SelectField<string> label={t("product.type")} value={type} onChange={setType} options={typeOptions(state)} />
        <TextField label={t("product.institution")} value={institution} onChange={setInstitution} invalid={!institution.trim()} />
        <span className="text-field-label">{t("product.share")}</span>
        <Stepper label={t("product.share")} value={share} step={5} min={1} max={100} inputMode="numeric" unit="%" onChange={setShare} />
        <div className="money-switch-row">
          <span className="money-switch-text">
            <span>{t("product.shared")}</span>
            <span className="money-switch-hint">{t("product.shared_hint")}</span>
          </span>
          <Switch label={t("product.shared")} checked={shared} onChange={setShared} />
        </div>
        {product.traits.length > 0 && <Hint>{product.traits.join(". ")}.</Hint>}
      </Section>

      <Section title={t("product.data_from")}>
        <List>
          <ListRow title={t("product.movements")} subtitle={product.movements_how} />
          {product.source && (
            <ListRow
              title={t("product.source_account")}
              subtitle={`${product.source.bank} · ${product.source.name}${product.source.iban_tail ? ` ···${product.source.iban_tail}` : ""}`}
            />
          )}
        </List>
        {!product.source && state.unmapped.length > 0 && (
          <SelectField<string>
            label={t("product.is_source")}
            value={source}
            onChange={setSource}
            options={[
              { value: "", label: t("product.none") },
              ...state.unmapped.map((u) => ({
                value: u.key,
                label: `${u.bank} · ${u.name}${u.iban_tail ? ` ···${u.iban_tail}` : ""}`,
              })),
            ]}
          />
        )}
      </Section>

      <Section title={t("product.ibans")}>
        <Hint>{t("product.ibans_hint")}</Hint>
        {ibans.length > 0 && (
          <List>
            {ibans.map((one) => (
              <div key={one} className="money-iban-row">
                <ListRow title={one} />
                <IconButton icon="close" label={t("product.remove_iban", { iban: one })} onClick={() => setIbans(ibans.filter((x) => x !== one))} />
              </div>
            ))}
          </List>
        )}
        <div className="money-search">
          <TextField label={t("product.add_iban")} value={iban} onChange={setIban} placeholder="ES00 0000 0000 0000 0000 0000" />
          <Button
            size="small"
            disabled={!iban.trim()}
            onClick={() => {
              const clean = iban.replace(/\s/g, "").toUpperCase();
              if (!ibans.includes(clean)) setIbans([...ibans, clean]);
              setIban("");
            }}
          >
            {t("product.add")}
          </Button>
        </div>
      </Section>

      {product.rules.length > 0 && (
        <Section title={t("product.rules")}>
          <List>
            {product.rules.map((r) => (
              <ListRow key={r.id} title={r.then} subtitle={capital(r.when)} value={movementsText(t, r.movements)} />
            ))}
          </List>
          <Hint>{t("product.rules_hint")}</Hint>
        </Section>
      )}
    </Sheet>
  );
}

function modeLabel(mode: string): string {
  return (VALUE_MODES.includes(mode) ? say(`mode.${mode}`) : mode).toLowerCase();
}

export function movementsText(t: Translate, n: number): string {
  return n === 1 ? t("movements.one") : t("movements.other", { count: n });
}

function typeOptions(state: State): { value: string; label: string }[] {
  return state.account_types.map((one) => ({ value: one.value, label: typeName(one.value, one.label) }));
}

function ValueEditor({ product, onBack, onSaved }: { product: ProductDetail; onBack: () => void; onSaved: (p: ProductDetail) => void }) {
  const t = useT();
  const [on, setOn] = useState(isoDay(new Date()));
  const [value, setValue] = useState(product.value !== null ? amountText(product.value) : "");
  const [problem, setProblem] = useState<string | null>(null);
  const amount = parseAmount(value);
  const save = async () => {
    if (amount === null || !on) return;
    try {
      onSaved(await api.setValue(product.key, on, String(amount)));
    } catch (e) {
      setProblem(problemOf(e));
    }
  };
  return (
    <Sheet title={t("value.title", { name: product.name })} onClose={onBack} action={{ label: t("value.record"), onClick: save, disabled: amount === null || !on }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <DateField label={t("value.day")} value={on} onChange={setOn} max={isoDay(new Date())} />
      <TextField label={t("value.value")} value={value} onChange={setValue} inputMode="decimal" invalid={value !== "" && amount === null} />
      <Hint>{t("value.hint")}</Hint>
    </Sheet>
  );
}

type Row = { id: number; name: string; amount: string };

function CompositionEditor({ product, onBack, onSaved }: { product: ProductDetail; onBack: () => void; onSaved: (p: ProductDetail) => void }) {
  const t = useT();
  const [on, setOn] = useState(isoDay(new Date()));
  const [by, setBy] = useState<"value" | "weight">("value");
  const [total, setTotal] = useState(product.value !== null ? amountText(product.value) : "");
  const [rows, setRows] = useState<Row[]>(() =>
    (product.photo?.funds ?? []).map((f, i) => ({ id: i, name: f.name, amount: amountText(f.value) })),
  );
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const nextId = () => Math.max(0, ...rows.map((r) => r.id)) + 1;
  const set = (id: number, patch: Partial<Row>) => setRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const amounts = rows.map((r) => parseAmount(r.amount));
  const sum = amounts.reduce<number>((s, a) => s + (a ?? 0), 0);
  const totalValue = parseAmount(total);
  const ready =
    rows.length > 0 && rows.every((r, i) => r.name.trim() && amounts[i] !== null) && !!on && (by === "value" || totalValue !== null);

  const save = async () => {
    setSaving(true);
    const funds: TypedFund[] = rows.map((r, i) =>
      by === "value" ? { name: r.name.trim(), value: String(amounts[i]) } : { name: r.name.trim(), weight: String(amounts[i]) },
    );
    try {
      onSaved(await api.setComposition(product.key, on, funds, by === "weight" ? String(totalValue) : undefined));
    } catch (e) {
      setProblem(problemOf(e));
      setSaving(false);
    }
  };

  return (
    <Sheet title={t("product.funds_of", { name: product.name })} onClose={onBack} action={{ label: t("common.save"), onClick: save, disabled: !ready || saving }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <DateField label={t("value.day")} value={on} onChange={setOn} max={isoDay(new Date())} />
      <SegmentedControl<"value" | "weight">
        label={t("composition.each_by")}
        value={by}
        onChange={setBy}
        options={[
          { value: "value", label: t("composition.money") },
          { value: "weight", label: t("composition.percent") },
        ]}
      />
      {by === "weight" && (
        <TextField label={t("composition.product_value")} value={total} onChange={setTotal} inputMode="decimal" invalid={total !== "" && totalValue === null} />
      )}
      {rows.map((r, i) => (
        <div key={r.id} className="money-fund-row">
          <TextField label={t("composition.fund")} value={r.name} onChange={(v) => set(r.id, { name: v })} invalid={!r.name.trim()} />
          <TextField
            label={by === "value" ? currencySymbol() : "%"}
            value={r.amount}
            onChange={(v) => set(r.id, { amount: v })}
            inputMode="decimal"
            invalid={r.amount !== "" && amounts[i] === null}
          />
          <IconButton icon="close" label={t("composition.remove", { name: r.name || t("composition.a_fund") })} onClick={() => setRows(rows.filter((x) => x.id !== r.id))} />
        </div>
      ))}
      <Button variant="plain" size="small" onClick={() => setRows([...rows, { id: nextId(), name: "", amount: "" }])}>
        {t("composition.add")}
      </Button>
      <Hint>
        {t("composition.sum", { amount: by === "value" ? money(sum, false) : percentText(sum / 100) })} {t("composition.name_hint")}
      </Hint>
    </Sheet>
  );
}

function FundEditor({ fund, state, onBack, onSaved }: { fund: FundRow; state: State; onBack: () => void; onSaved: () => void }) {
  const t = useT();
  const [asset, setAsset] = useState(fund.asset === "other" && fund.classified === "unknown" ? "equity" : fund.asset);
  const [weights, setWeights] = useState<Record<string, number | null>>(() =>
    Object.fromEntries(state.regions.map((r) => [r.value, fund.regions.find((x) => x.key === r.value)?.weight ?? 0])),
  );
  const [problem, setProblem] = useState<string | null>(null);
  const sum = Object.values(weights).reduce<number>((s, w) => s + (w ?? 0), 0);
  const splits = asset !== "cash" && asset !== "crypto";
  const ready = !splits || sum === 0 || Math.abs(sum - 100) < 0.5;

  const save = async () => {
    try {
      const regions = splits ? Object.fromEntries(Object.entries(weights).filter(([, w]) => (w ?? 0) > 0).map(([k, w]) => [k, w ?? 0])) : {};
      await api.classifyFund(fund.symbol, asset, regions);
      onSaved();
    } catch (e) {
      setProblem(problemOf(e));
    }
  };
  const reset = async () => {
    try {
      await api.unclassifyFund(fund.symbol);
      onSaved();
    } catch (e) {
      setProblem(problemOf(e));
    }
  };

  return (
    <Sheet title={fund.name} onClose={onBack} action={{ label: t("common.save"), onClick: save, disabled: !ready }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {fund.classified === "unknown" && (
        <Notice tone="warning" title={t("fund.unclassified")}>
          {t("fund.unclassified_body")}
        </Notice>
      )}
      <SelectField<string> label={t("fund.asset")} value={asset} onChange={setAsset} options={state.assets} />
      {splits && (
        <>
          {state.regions.map((r) => (
            <div key={r.value}>
              <span className="text-field-label">{r.label}</span>
              <Stepper
                label={r.label}
                value={weights[r.value] ?? 0}
                step={5}
                min={0}
                max={100}
                inputMode="numeric"
                unit="%"
                onChange={(v) => setWeights({ ...weights, [r.value]: v })}
              />
            </div>
          ))}
          <Hint tone={ready ? undefined : "warning"}>
            {t(ready ? "fund.sum" : "fund.sum_wrong", { percent: percentText(Math.round(sum) / 100) })}
          </Hint>
        </>
      )}
      {fund.classified === "yours" && (
        <Button variant="plain" size="small" onClick={reset}>
          {t("fund.reset")}
        </Button>
      )}
      <Hint>{t("fund.hint")}</Hint>
    </Sheet>
  );
}

export function NewProductSheet({ state, onClose, onCreated }: { state: State; onClose: () => void; onCreated: (key: string) => void }) {
  const t = useT();
  const toast = useToast();
  const [name, setName] = useState("");
  const [type, setType] = useState("fund");
  const [institution, setInstitution] = useState("");
  const [share, setShare] = useState<number | null>(100);
  const [source, setSource] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const valid = name.trim() && institution.trim() && share !== null && share >= 1 && share <= 100;

  const create = async () => {
    if (!valid || share === null) return;
    setSaving(true);
    try {
      const created = await api.addProduct({
        name: name.trim(),
        type,
        institution: institution.trim(),
        ownership: share / 100,
        shared: false,
        ibans: [],
        ...(source ? { source } : {}),
      });
      toast({ message: t("new.created") });
      onCreated(created.key);
    } catch (e) {
      setProblem(problemOf(e));
      setSaving(false);
    }
  };

  return (
    <Sheet title={t("new.title")} onClose={onClose} action={{ label: t("new.create"), onClick: create, disabled: !valid || saving }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <TextField label={t("product.name")} value={name} onChange={setName} autoFocus placeholder={t("new.placeholder")} />
      <SelectField<string> label={t("product.type")} value={type} onChange={setType} options={typeOptions(state)} />
      <TextField label={t("product.institution")} value={institution} onChange={setInstitution} />
      <span className="text-field-label">{t("product.share")}</span>
      <Stepper label={t("product.share")} value={share} step={5} min={1} max={100} inputMode="numeric" unit="%" onChange={setShare} />
      {state.unmapped.length > 0 && (
        <SelectField<string>
          label={t("new.data_from")}
          value={source}
          onChange={setSource}
          options={[
            { value: "", label: t("new.from_transfers") },
            ...state.unmapped.map((u) => ({ value: u.key, label: `${u.bank} · ${u.name}${u.iban_tail ? ` ···${u.iban_tail}` : ""}` })),
          ]}
        />
      )}
      <Hint>
        {t("new.hint")}
      </Hint>
    </Sheet>
  );
}
