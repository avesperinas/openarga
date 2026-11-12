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
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { signedPercent } from "./analysisParts";
import { type FundRow, type ProductChange, type ProductDetail, Refused, type State, type TypedFund, api } from "./api";
import { amountText, capital, isoDay, money, parseAmount, shortDay } from "./format";

const VALUE_MODES = [
  { value: "balance", label: "El saldo de su fuente" },
  { value: "computed", label: "La suma de sus movimientos" },
  { value: "snapshot", label: "La foto de su fuente" },
  { value: "manual", label: "Lo que yo apunte" },
];

function problemOf(e: unknown): string {
  return e instanceof Refused ? capital(e.message) : "No se ha podido guardar.";
}

function fundLine(f: FundRow): string {
  const parts = [f.asset_name];
  if (f.regions.length) parts.push(f.regions.map((r) => `${r.name} ${Math.round(r.weight)} %`).join(", "));
  if (f.classified === "unknown") parts.push("sin clasificar");
  if (f.classified === "yours") parts.push("clasificado por ti");
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
  const toast = useToast();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: "detail" });
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    api.product(productKey).then(setProduct, () => setProblem("No se ha podido abrir."));
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
      <Sheet title="Producto" onClose={onClose}>
        {problem ? <Hint tone="warning">{problem}</Hint> : <Hint>Cargando…</Hint>}
      </Sheet>
    );

  const back = () => {
    setMode({ kind: "detail" });
    setProblem(null);
  };
  if (mode.kind === "composition")
    return <CompositionEditor product={product} onBack={back} onSaved={(p) => saved(p, "Composición guardada")} />;
  if (mode.kind === "fund")
    return (
      <FundEditor
        fund={mode.fund}
        state={state}
        onBack={back}
        onSaved={async () => saved(await api.product(product.key), "Fondo guardado")}
      />
    );
  if (mode.kind === "value")
    return <ValueEditor product={product} onBack={back} onSaved={(p) => saved(p, "Valor apuntado")} />;
  return (
    <DetailEditor
      product={product}
      state={state}
      onClose={onClose}
      onSaved={(p) => saved(p, "Producto guardado")}
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
  const since = product.value_since ? ` · desde ${shortDay(product.value_since)}` : "";

  return (
    <Sheet title={product.name} onClose={onClose} action={{ label: "Guardar", onClick: save, disabled: !valid || !changed || saving }}>
      {problem && <Hint tone="warning">{problem}</Hint>}

      <Section title="Su valor">
        <List>
          <ListRow
            title="Vale"
            value={product.value === null ? "Sin valor aún" : money(product.value, false)}
            detail={product.estimated ? `estimado a ${shortDay(product.estimated)}` : undefined}
          />
          {product.contributed !== null && <ListRow title="Aportado" value={money(product.contributed, false)} />}
        </List>
        <Hint>
          Cómo se calcula: {product.value_how.charAt(0).toLowerCase()}
          {product.value_how.slice(1)}
          {since}.
        </Hint>
        <SelectField<string>
          label="Cómo se valora"
          value={valueMode}
          onChange={setValueMode}
          options={[{ value: "", label: `Como ahora: ${modeLabel(product.value_mode)}` }, { value: "type", label: "La de su tipo" }, ...VALUE_MODES]}
        />
        <Button variant="tinted" size="small" onClick={() => onMode({ kind: "value" })}>
          Apuntar lo que vale
        </Button>
      </Section>

      {invested && (
        <Section title={product.photo ? `Sus fondos a ${shortDay(product.photo.on)}` : "Sus fondos"}>
          {product.photo ? (
            <List>
              {product.photo.funds.map((f) => (
                <FundListRow key={f.symbol} fund={f} onClick={() => onMode({ kind: "fund", fund: f })} />
              ))}
            </List>
          ) : (
            <Hint>Aún no sabe en qué fondos está. Apúntalo, o sube su cartera en Hub.</Hint>
          )}
          {product.photo?.typed && <Hint>Esta foto la apuntaste tú: manda sobre la de su fuente del mismo día.</Hint>}
          {product.photo && <Hint>Toca un fondo para decir qué es. El valor de cada uno se mueve con su precio desde la foto.</Hint>}
          <Button variant="tinted" size="small" onClick={() => onMode({ kind: "composition" })}>
            Apuntar su composición
          </Button>
          {product.photo?.typed && (
            <Button variant="plain" size="small" onClick={removeTyped}>
              Quitar la composición apuntada
            </Button>
          )}
        </Section>
      )}

      <Section title="Qué es">
        <TextField label="Nombre" value={name} onChange={setName} invalid={!name.trim()} />
        <SelectField<string> label="Tipo" value={type} onChange={setType} options={state.account_types} />
        <TextField label="Entidad" value={institution} onChange={setInstitution} invalid={!institution.trim()} />
        <span className="text-field-label">Parte tuya</span>
        <Stepper label="Parte tuya" value={share} step={5} min={1} max={100} inputMode="numeric" unit="%" onChange={setShare} />
        <div className="money-switch-row">
          <span className="money-switch-text">
            <span>Cuenta común</span>
            <span className="money-switch-hint">Lo que se paga desde ella va a Compartido.</span>
          </span>
          <Switch label="Cuenta común" checked={shared} onChange={setShared} />
        </div>
        {product.traits.length > 0 && <Hint>{product.traits.join(". ")}.</Hint>}
      </Section>

      <Section title="De dónde llegan sus datos">
        <List>
          <ListRow title="Sus movimientos" subtitle={product.movements_how} />
          {product.source && (
            <ListRow
              title="Su cuenta en la fuente"
              subtitle={`${product.source.bank} · ${product.source.name}${product.source.iban_tail ? ` ···${product.source.iban_tail}` : ""}`}
            />
          )}
        </List>
        {!product.source && state.unmapped.length > 0 && (
          <SelectField<string>
            label="Es esta cuenta de tus fuentes"
            value={source}
            onChange={setSource}
            options={[
              { value: "", label: "Ninguna" },
              ...state.unmapped.map((u) => ({
                value: u.key,
                label: `${u.bank} · ${u.name}${u.iban_tail ? ` ···${u.iban_tail}` : ""}`,
              })),
            ]}
          />
        )}
      </Section>

      <Section title="Sus IBAN">
        <Hint>Un movimiento de otra cuenta tuya hacia uno de estos IBAN es un traspaso a este producto.</Hint>
        {ibans.length > 0 && (
          <List>
            {ibans.map((one) => (
              <div key={one} className="money-iban-row">
                <ListRow title={one} />
                <IconButton icon="close" label={`Quitar ${one}`} onClick={() => setIbans(ibans.filter((x) => x !== one))} />
              </div>
            ))}
          </List>
        )}
        <div className="money-search">
          <TextField label="Añadir IBAN" value={iban} onChange={setIban} placeholder="ES00 0000 0000 0000 0000 0000" />
          <Button
            size="small"
            disabled={!iban.trim()}
            onClick={() => {
              const clean = iban.replace(/\s/g, "").toUpperCase();
              if (!ibans.includes(clean)) setIbans([...ibans, clean]);
              setIban("");
            }}
          >
            Añadir
          </Button>
        </div>
      </Section>

      {product.rules.length > 0 && (
        <Section title="Reglas que lo nombran">
          <List>
            {product.rules.map((r) => (
              <ListRow key={r.id} title={r.then} subtitle={capital(r.when)} value={movementsText(r.movements)} />
            ))}
          </List>
          <Hint>Se quitan en Ajustes › Reglas.</Hint>
        </Section>
      )}
    </Sheet>
  );
}

function modeLabel(mode: string): string {
  return (VALUE_MODES.find((m) => m.value === mode)?.label ?? mode).toLowerCase();
}

export function movementsText(n: number): string {
  return n === 1 ? "1 movimiento" : `${n} movimientos`;
}

function ValueEditor({ product, onBack, onSaved }: { product: ProductDetail; onBack: () => void; onSaved: (p: ProductDetail) => void }) {
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
    <Sheet title={`Lo que vale ${product.name}`} onClose={onBack} action={{ label: "Apuntar", onClick: save, disabled: amount === null || !on }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <DateField label="Día" value={on} onChange={setOn} max={isoDay(new Date())} />
      <TextField label="Valor" value={value} onChange={setValue} inputMode="decimal" invalid={value !== "" && amount === null} />
      <Hint>Desde ese día, el producto parte de este valor. Si su fuente da otro el mismo día, manda el de la fuente.</Hint>
    </Sheet>
  );
}

type Row = { id: number; name: string; amount: string };

function CompositionEditor({ product, onBack, onSaved }: { product: ProductDetail; onBack: () => void; onSaved: (p: ProductDetail) => void }) {
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
    <Sheet title={`Fondos de ${product.name}`} onClose={onBack} action={{ label: "Guardar", onClick: save, disabled: !ready || saving }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <DateField label="Día" value={on} onChange={setOn} max={isoDay(new Date())} />
      <SegmentedControl<"value" | "weight">
        label="Cada fondo, por"
        value={by}
        onChange={setBy}
        options={[
          { value: "value", label: "Euros" },
          { value: "weight", label: "Porcentaje" },
        ]}
      />
      {by === "weight" && (
        <TextField label="Lo que vale el producto" value={total} onChange={setTotal} inputMode="decimal" invalid={total !== "" && totalValue === null} />
      )}
      {rows.map((r, i) => (
        <div key={r.id} className="money-fund-row">
          <TextField label="Fondo" value={r.name} onChange={(v) => set(r.id, { name: v })} invalid={!r.name.trim()} />
          <TextField
            label={by === "value" ? "€" : "%"}
            value={r.amount}
            onChange={(v) => set(r.id, { amount: v })}
            inputMode="decimal"
            invalid={r.amount !== "" && amounts[i] === null}
          />
          <IconButton icon="close" label={`Quitar ${r.name || "fondo"}`} onClick={() => setRows(rows.filter((x) => x.id !== r.id))} />
        </div>
      ))}
      <Button variant="plain" size="small" onClick={() => setRows([...rows, { id: nextId(), name: "", amount: "" }])}>
        + Añadir fondo
      </Button>
      <Hint>
        {by === "value" ? `Suman ${money(sum, false)}.` : `Suman ${amountText(sum)} %.`} El nombre, tal como lo enseña tu entidad: se reconoce aunque
        cambie «Hedged» o «Fund». La liquidez es «Liquidez».
      </Hint>
    </Sheet>
  );
}

function FundEditor({ fund, state, onBack, onSaved }: { fund: FundRow; state: State; onBack: () => void; onSaved: () => void }) {
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
    <Sheet title={fund.name} onClose={onBack} action={{ label: "Guardar", onClick: save, disabled: !ready }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {fund.classified === "unknown" && (
        <Notice tone="warning" title="Sin clasificar">
          No está en el catálogo: dime qué es para repartirlo en la composición.
        </Notice>
      )}
      <SelectField<string> label="Clase de activo" value={asset} onChange={setAsset} options={state.assets} />
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
            Suman {Math.round(sum)} %{ready ? "" : ": tienen que sumar 100 %, o nada si no quieres repartirlo"}.
          </Hint>
        </>
      )}
      {fund.classified === "yours" && (
        <Button variant="plain" size="small" onClick={reset}>
          Volver a lo que dice el catálogo
        </Button>
      )}
      <Hint>Lo que digas vale para este fondo en todos tus productos.</Hint>
    </Sheet>
  );
}

export function NewProductSheet({ state, onClose, onCreated }: { state: State; onClose: () => void; onCreated: (key: string) => void }) {
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
      toast({ message: "Producto creado" });
      onCreated(created.key);
    } catch (e) {
      setProblem(problemOf(e));
      setSaving(false);
    }
  };

  return (
    <Sheet title="Nuevo producto" onClose={onClose} action={{ label: "Crear", onClick: create, disabled: !valid || saving }}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <TextField label="Nombre" value={name} onChange={setName} autoFocus placeholder="Fianza del piso, Fondo indexado…" />
      <SelectField<string> label="Tipo" value={type} onChange={setType} options={state.account_types} />
      <TextField label="Entidad" value={institution} onChange={setInstitution} />
      <span className="text-field-label">Parte tuya</span>
      <Stepper label="Parte tuya" value={share} step={5} min={1} max={100} inputMode="numeric" unit="%" onChange={setShare} />
      {state.unmapped.length > 0 && (
        <SelectField<string>
          label="Sus datos llegan de"
          value={source}
          onChange={setSource}
          options={[
            { value: "", label: "De los traspasos desde mis cuentas" },
            ...state.unmapped.map((u) => ({ value: u.key, label: `${u.bank} · ${u.name}${u.iban_tail ? ` ···${u.iban_tail}` : ""}` })),
          ]}
        />
      )}
      <Hint>
        Sin una cuenta de tus fuentes, sus movimientos salen de los traspasos desde tus otras cuentas: dale sus IBAN en su ficha, o marca
        el movimiento como traspaso a él. Una fianza vale lo que se ha ido a ella menos lo que ha vuelto.
      </Hint>
    </Sheet>
  );
}
