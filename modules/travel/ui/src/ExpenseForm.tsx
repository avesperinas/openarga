import { Button, ChoiceChips, DateField, Hint, SegmentedControl, SelectField, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Category, type ExpenseIn, type Traveller, type Trip, readConcepts, readTravellers } from "./api";
import { travellerLabel, useMembers } from "./people";
import { CATEGORIES, todayIso } from "./words";

export const CURRENCIES = [
  "EUR", "USD", "GBP", "JPY", "CHF", "SEK", "NOK", "DKK", "ISK", "CZK", "HUF", "PLN", "RON", "TRY",
  "CAD", "MXN", "BRL", "AUD", "NZD", "CNY", "HKD", "KRW", "SGD", "THB", "IDR", "MYR", "PHP", "INR",
  "ZAR", "ILS",
];
const OTHER = "otra";

type Mode = "paid" | "per_person";

export function parseAmount(text: string): number | null {
  const raw = text.trim();
  if (!raw) return null;
  const thousands = /^\d{1,3}(\.\d{3})+$/.test(raw);
  const normal = raw.includes(",") || thousands ? raw.replace(/\./g, "").replace(",", ".") : raw;
  const value = Number(normal);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) / 100 : null;
}

export function ExpenseForm({
  trip,
  onSave,
  needsRate,
  compact = false,
}: {
  trip: Trip;
  onSave: (expense: ExpenseIn) => Promise<boolean>;
  needsRate?: boolean;
  compact?: boolean;
}) {
  const [mode, setMode] = useState<Mode>(trip.phase === "done" ? "per_person" : "paid");
  const [concepts, setConcepts] = useState<Record<Category, string[]> | null>(null);
  const [people, setPeople] = useState<Traveller[]>([]);
  const [category, setCategory] = useState<Category>(compact ? "other" : "transport");
  const [concept, setConcept] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(() => {
    try {
      return localStorage.getItem(`travel-currency-${trip.id}`) ?? "EUR";
    } catch {
      return "EUR";
    }
  });
  const [custom, setCustom] = useState("");
  const [payer, setPayer] = useState<string | null>(null);
  const [day, setDay] = useState(() => {
    const today = todayIso();
    return today >= trip.starts_on && today <= trip.ends_on ? today : trip.starts_on;
  });
  const [rate, setRate] = useState("");
  const [split, setSplit] = useState<"equal" | "custom">("equal");
  const [parts, setParts] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const members = useMembers(trip.space_id);

  useEffect(() => {
    readConcepts()
      .then(setConcepts)
      .catch(() => setConcepts(null));
    readTravellers(trip.id)
      .then((found) => {
        setPeople(found);
        setPayer((now) => now ?? found.find((one) => one.me)?.id ?? null);
      })
      .catch(() => setPeople([]));
  }, [trip.id]);

  const value = parseAmount(amount);
  const code = currency === OTHER ? custom.trim().toUpperCase() : currency;
  const manual = parseAmount(rate);
  const askRate = mode === "paid" && code !== "EUR" && (needsRate || !CURRENCIES.includes(code));
  const byParts = mode === "paid" && split === "custom";
  const partsTotal = people.reduce((sum, one) => sum + (parseAmount(parts[one.id] ?? "") ?? 0), 0);
  const partsMatch = !byParts || (value !== null && Math.abs(partsTotal - value) < 0.005);
  const ready =
    Boolean(concept.trim()) &&
    value !== null &&
    !busy &&
    partsMatch &&
    (mode === "per_person" || (/^[A-Z]{3}$/.test(code) && (!askRate || (manual !== null && manual > 0))));

  const save = async () => {
    setBusy(true);
    const base = { category, concept: concept.trim(), note: note.trim() || null };
    const sent: ExpenseIn =
      mode === "per_person"
        ? { ...base, amount_eur: value!.toFixed(2) }
        : {
            ...base,
            amount: value!.toFixed(2),
            currency: code,
            paid_by: payer,
            spent_on: day,
            fx_rate: askRate && manual ? String(manual) : null,
            shares: byParts
              ? people
                  .map((one) => ({ traveller_id: one.id, amount: (parseAmount(parts[one.id] ?? "") ?? 0).toFixed(2) }))
                  .filter((one) => Number(one.amount) > 0)
              : null,
          };
    try {
      if (mode === "paid") localStorage.setItem(`travel-currency-${trip.id}`, currency);
    } catch {
    }
    const saved = await onSave(sent);
    setBusy(false);
    if (saved) {
      setAmount("");
      setNote("");
      setConcept("");
      setRate("");
      setParts({});
    }
  };

  return (
    <div className="surface travel-form">
      <SegmentedControl
        label="Cómo lo apuntas"
        value={mode}
        onChange={setMode}
        options={[
          { value: "paid", label: "Lo pagado" },
          { value: "per_person", label: "Por persona (€)" },
        ]}
      />
      <SegmentedControl
        label="Categoría"
        value={category}
        onChange={(next) => {
          setCategory(next);
          setConcept("");
        }}
        options={(Object.keys(CATEGORIES) as Category[]).map((one) => ({ value: one, label: CATEGORIES[one] }))}
      />
      {concepts && (
        <ChoiceChips
          label="Concepto sugerido"
          value={concepts[category].includes(concept) ? concept : null}
          onChange={setConcept}
          options={concepts[category].map((one) => ({ value: one, label: one }))}
        />
      )}
      <TextField label="Concepto" value={concept} onChange={setConcept} />
      {mode === "paid" ? (
        <>
          <div className="travel-form-row">
            <TextField
              label="Lo pagado"
              inputMode="decimal"
              value={amount}
              onChange={setAmount}
              invalid={amount !== "" && value === null}
              hint="El total, no por persona"
            />
            <SelectField
              label="Moneda"
              value={currency}
              onChange={setCurrency}
              options={[...CURRENCIES.map((one) => ({ value: one, label: one })), { value: OTHER, label: "Otra…" }]}
            />
          </div>
          {currency === OTHER && (
            <TextField label="Código de la moneda" value={custom} onChange={setCustom} placeholder="VND, PEN, MAD…" />
          )}
          {askRate && (
            <TextField
              label={`Euros por 1 ${code || "unidad"}`}
              inputMode="decimal"
              value={rate}
              onChange={setRate}
              hint="El BCE no publica el cambio de esta moneda: ponlo tú."
            />
          )}
          {people.length > 0 && (
            <div className="travel-field">
              <span className="travel-field-label">Quién pagó</span>
              <ChoiceChips
                label="Quién pagó"
                value={payer}
                onChange={setPayer}
                options={people.map((one) => ({ value: one.id, label: travellerLabel(one, members) }))}
              />
            </div>
          )}
          <DateField label="Día" value={day} onChange={setDay} min={trip.starts_on} max={trip.ends_on} />
          {people.length > 1 && (
            <SegmentedControl
              label="Reparto"
              value={split}
              onChange={setSplit}
              options={[
                { value: "equal", label: "A partes iguales" },
                { value: "custom", label: "A medida" },
              ]}
            />
          )}
          {byParts && (
            <>
              <div className="travel-parts">
                {people.map((one) => (
                  <TextField
                    key={one.id}
                    label={travellerLabel(one, members)}
                    inputMode="decimal"
                    value={parts[one.id] ?? ""}
                    onChange={(next) => setParts({ ...parts, [one.id]: next })}
                  />
                ))}
              </div>
              <Hint tone={partsMatch ? undefined : "warning"}>
                {value === null
                  ? "Pon lo pagado y la parte de cada uno."
                  : partsMatch
                    ? "Las partes suman lo pagado."
                    : `Las partes suman ${partsTotal.toFixed(2)} y lo pagado es ${value.toFixed(2)} ${code}.`}
              </Hint>
            </>
          )}
        </>
      ) : (
        <>
          <TextField
            label="Importe por persona (€)"
            inputMode="decimal"
            value={amount}
            onChange={setAmount}
            invalid={amount !== "" && value === null}
          />
          <Hint>Como en la hoja: por persona y ya en euros. Sois {trip.travellers}.</Hint>
        </>
      )}
      {!compact && <TextField label="Nota" value={note} onChange={setNote} />}
      <Button variant="primary" icon="plus" disabled={!ready} onClick={() => void save()}>
        Apuntar gasto
      </Button>
    </div>
  );
}
