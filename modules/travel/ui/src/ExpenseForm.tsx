import { Button, ChoiceChips, DateField, Hint, SegmentedControl, SelectField, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Category, type ExpenseIn, type Traveller, type Trip, readConcepts, readTravellers } from "./api";
import { travellerLabel, useMembers } from "./people";
import { CATEGORIES, todayIso } from "./words";
import { t } from "./lang";

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
        label={t("expense.how")}
        value={mode}
        onChange={setMode}
        options={[
          { value: "paid", label: t("expense.paid") },
          { value: "per_person", label: t("expense.per_person") },
        ]}
      />
      <SegmentedControl
        label={t("expense.category")}
        value={category}
        onChange={(next) => {
          setCategory(next);
          setConcept("");
        }}
        options={(Object.keys(CATEGORIES) as Category[]).map((one) => ({ value: one, label: CATEGORIES[one] }))}
      />
      {concepts && (
        <ChoiceChips
          label={t("expense.suggested")}
          value={concepts[category].includes(concept) ? concept : null}
          onChange={setConcept}
          options={concepts[category].map((one) => ({ value: one, label: one }))}
        />
      )}
      <TextField label={t("expense.concept")} value={concept} onChange={setConcept} />
      {mode === "paid" ? (
        <>
          <div className="travel-form-row">
            <TextField
              label={t("expense.paid")}
              inputMode="decimal"
              value={amount}
              onChange={setAmount}
              invalid={amount !== "" && value === null}
              hint={t("expense.paid_hint")}
            />
            <SelectField
              label={t("expense.currency")}
              value={currency}
              onChange={setCurrency}
              options={[...CURRENCIES.map((one) => ({ value: one, label: one })), { value: OTHER, label: t("expense.other_currency") }]}
            />
          </div>
          {currency === OTHER && (
            <TextField label={t("expense.currency_code")} value={custom} onChange={setCustom} placeholder="VND, PEN, MAD…" />
          )}
          {askRate && (
            <TextField
              label={t("expense.rate", { code: code || t("expense.unit") })}
              inputMode="decimal"
              value={rate}
              onChange={setRate}
              hint={t("expense.rate_hint")}
            />
          )}
          {people.length > 0 && (
            <div className="travel-field">
              <span className="travel-field-label">{t("bookings.payer")}</span>
              <ChoiceChips
                label={t("bookings.payer")}
                value={payer}
                onChange={setPayer}
                options={people.map((one) => ({ value: one.id, label: travellerLabel(one, members) }))}
              />
            </div>
          )}
          <DateField label={t("editor.day")} value={day} onChange={setDay} min={trip.starts_on} max={trip.ends_on} />
          {people.length > 1 && (
            <SegmentedControl
              label={t("expense.split")}
              value={split}
              onChange={setSplit}
              options={[
                { value: "equal", label: t("expense.equal") },
                { value: "custom", label: t("expense.custom") },
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
                  ? t("expense.parts_missing")
                  : partsMatch
                    ? t("expense.parts_match")
                    : t("expense.parts_differ", { parts: partsTotal.toFixed(2), paid: `${value.toFixed(2)} ${code}` })}
              </Hint>
            </>
          )}
        </>
      ) : (
        <>
          <TextField
            label={t("expense.amount_per_person")}
            inputMode="decimal"
            value={amount}
            onChange={setAmount}
            invalid={amount !== "" && value === null}
          />
          <Hint>{t("expense.per_person_hint", { count: trip.travellers })}</Hint>
        </>
      )}
      {!compact && <TextField label={t("editor.note")} value={note} onChange={setNote} />}
      <Button variant="primary" icon="plus" disabled={!ready} onClick={() => void save()}>
        {t("today.note_spend")}
      </Button>
    </div>
  );
}
