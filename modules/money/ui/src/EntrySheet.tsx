import { DateField, Hint, SegmentedControl, SelectField, Sheet, TextField } from "@openarga/ui";
import { useState } from "react";

import { Refused, type State, api } from "./api";
import { isoDay, parseAmount } from "./format";

export function EntrySheet({
  state,
  year,
  names,
  common,
  onClose,
  onSaved,
}: {
  state: State;
  year: number;
  names?: { me: string; other: string };
  common?: { name: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const shared = common
    ? common.map((c) => ({ id: c.name, name: c.name }))
    : state.categories.filter((c) => c.nature === "expense" && c.ownership === "shared");
  const me = names?.me ?? state.me;
  const other = names?.other ?? state.other;
  const today = new Date();
  const [payer, setPayer] = useState<"me" | "other">("other");
  const [on, setOn] = useState(isoDay(today.getFullYear() === year ? today : new Date(year, 11, 31)));
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState(shared[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const value = parseAmount(amount);
  const ready = !!value && value > 0 && description.trim() && category && on;

  const save = async () => {
    if (!ready) return;
    setSaving(true);
    setError(null);
    try {
      await api.addEntry({ payer, on, amount: String(value), description: description.trim(), category });
      onSaved();
    } catch (e) {
      setError(e instanceof Refused ? e.message : "No se ha podido guardar.");
      setSaving(false);
    }
  };

  return (
    <Sheet title="Gasto fuera de cuenta" onClose={onClose} action={{ label: saving ? "Guardando…" : "Apuntar", onClick: save, disabled: !ready || saving }}>
      <div className="money-form">
        <SegmentedControl<"me" | "other">
          label="Quién lo pagó"
          value={payer}
          onChange={setPayer}
          options={[
            { value: "other", label: other },
            { value: "me", label: me },
          ]}
        />
        <TextField label="Qué fue" value={description} onChange={setDescription} placeholder="Luz de septiembre" autoFocus />
        <div className="money-pair">
          <TextField label="Importe" value={amount} onChange={setAmount} inputMode="decimal" placeholder="0,00" invalid={!!amount && !value} />
          <DateField label="Fecha" value={on} onChange={setOn} />
        </div>
        <SelectField<string>
          label="Categoría"
          value={category}
          onChange={setCategory}
          options={shared.map((c) => ({ value: c.id, label: c.name }))}
        />
        <Hint>
          {payer === "other"
            ? `Cuenta como pagado por ${other}: su parte sube y la tuya también, según la categoría.`
            : "Lo tuyo en efectivo sin retirada que lo explique. Si salió de un cajero, mejor etiqueta la retirada."}
        </Hint>
        {error && <Hint tone="warning">{error}</Hint>}
      </div>
    </Sheet>
  );
}
