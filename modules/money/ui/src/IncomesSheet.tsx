import { Button, ConfirmPanel, DateField, Hint, SegmentedControl, SelectField, Sheet, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Income, type IncomeSource, type Person, Refused, type Shared, type Space, api } from "./api";
import { amountText, money, parseAmount, shortDay } from "./format";

const PEOPLE: Person[] = ["me", "other"];

export function carreraNote(data: Pick<Shared, "year" | "carrera" | "space_id">, person: Person, spaceChosen: boolean): string {
  const value = data.carrera[person];
  if (value !== null) {
    return person === "me"
      ? `${money(value, false)} netos en ${data.year}, cobrado y lo que queda hasta diciembre.`
      : `${money(value, false)} netos en ${data.year}, lo que comparte desde su Carrera.`;
  }
  if (person === "me") return `Carrera aún no tiene tu neto de ${data.year}: cuentan tus tramos.`;
  if (!spaceChosen) return "Elige abajo el espacio que compartís. Hasta entonces, cuentan sus tramos.";
  return `Aún no lo comparte: tiene que elegir este espacio y «De Carrera» para ${data.year} en su Money. Hasta entonces, cuentan sus tramos.`;
}

export const sourceLabel = (source: IncomeSource) => (source === "carrera" ? "De Carrera" : "A mano");

interface Row {
  person: "me" | "other";
  from: string;
  to: string;
  salary: string;
  extra: string;
}

export function IncomesSheet({ data, onClose, onSaved }: { data: Shared; onClose: () => void; onSaved: () => void }) {
  const [rows, setRows] = useState<Row[]>(() =>
    data.incomes.length
      ? data.incomes.map((i) => ({ ...i, salary: amountText(i.salary), extra: i.extra ? amountText(i.extra) : "" }))
      : (["me", "other"] as const).map((person) => ({ person, from: `${data.year}-01-01`, to: `${data.year}-12-31`, salary: "", extra: "" })),
  );
  const [sources, setSources] = useState(data.income_sources);
  const [space, setSpace] = useState<string>(data.space_id ?? "");
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => {
    api.spaces().then(setSpaces, () => setSpaces([]));
  }, []);
  const filled = rows.filter((r) => r.salary.trim() !== "");
  const valid = filled.every((r) => r.from && r.to && r.from <= r.to && parseAmount(r.salary) !== null && (!r.extra || parseAmount(r.extra) !== null));

  const save = async () => {
    const incomes: Income[] = filled.map((r) => ({
      person: r.person,
      from: r.from,
      to: r.to,
      salary: parseAmount(r.salary) ?? 0,
      extra: r.extra ? (parseAmount(r.extra) ?? 0) : 0,
    }));
    try {
      if ((data.space_id ?? "") !== space) await api.sharedSpace(space || null);
      if (PEOPLE.some((p) => sources[p] !== data.income_sources[p])) await api.incomeSources(data.year, sources);
      await api.incomes(data.year, incomes);
      onSaved();
    } catch (e) {
      setError(e instanceof Refused ? e.message : "No se ha podido guardar.");
    }
  };

  const set = (i: number, patch: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const who = (person: "me" | "other") => (person === "me" ? data.me : data.other);
  const spaceName = (id: string) => (id ? (spaces.find((s) => s.id === id)?.name ?? "Un espacio") : "Ninguno");
  const before = (person: "me" | "other") =>
    data.incomes.filter((i) => i.person === person).map((i) => `${money(i.salary, false)} (${shortDay(i.from)}–${shortDay(i.to)})`).join(", ") || "Nada";
  const after = (person: "me" | "other") =>
    filled.filter((r) => r.person === person).map((r) => `${money(parseAmount(r.salary) ?? 0, false)} (${shortDay(r.from)}–${shortDay(r.to)})`).join(", ") || "Nada";

  if (confirming) {
    return (
      <Sheet title={`Ingresos de ${data.year}`} onClose={onClose}>
        <ConfirmPanel
          title="¿Guardar los ingresos declarados?"
          changes={[
            ...PEOPLE.filter((p) => sources[p] !== data.income_sources[p]).map((p) => ({
              label: `De dónde sale lo de ${who(p)}`,
              from: sourceLabel(data.income_sources[p]),
              to: sourceLabel(sources[p]),
            })),
            ...((data.space_id ?? "") !== space
              ? [{ label: "Espacio compartido", from: spaceName(data.space_id ?? ""), to: spaceName(space) }]
              : []),
            ...PEOPLE.map((p) => ({ label: `Tramos de ${who(p)}`, from: before(p), to: after(p) })),
          ]}
          detail="Cambian el reparto de lo proporcional de todo el año, y con él el saldo."
          action="Guardar ingresos"
          onCancel={() => setConfirming(false)}
          onConfirm={save}
        />
      </Sheet>
    );
  }

  return (
    <Sheet title={`Ingresos de ${data.year}`} onClose={onClose} action={{ label: "Guardar", onClick: () => setConfirming(true), disabled: !valid }}>
      <div className="money-form">
        {PEOPLE.map((p) => (
          <div key={p} className="surface money-part-edit">
            <SegmentedControl<IncomeSource>
              label={`Ingresos de ${who(p)} en ${data.year}`}
              value={sources[p]}
              onChange={(source) => setSources({ ...sources, [p]: source })}
              options={[
                { value: "typed", label: "A mano" },
                { value: "carrera", label: p === "me" ? "De Carrera" : "De su Carrera" },
              ]}
            />
            {sources[p] === "carrera" && (
              <Hint tone={data.carrera[p] === null ? "warning" : undefined}>{carreraNote(data, p, !!space)}</Hint>
            )}
          </div>
        ))}
        {spaces.length > 0 && (
          <>
            <SelectField<string>
              label="Espacio compartido"
              value={space}
              onChange={setSpace}
              options={[{ value: "", label: "Ninguno" }, ...spaces.map((s) => ({ value: s.id, label: s.name }))]}
            />
            <Hint>
              Con un espacio elegido, tu neto de Carrera de cada año en el que elijas «De Carrera» queda en él, y la otra persona puede usarlo. Nada más
              sale de tu Money.
            </Hint>
          </>
        )}
        {rows.map((r, i) => (
          <div key={i} className="surface money-part-edit">
            <SegmentedControl<"me" | "other">
              label="De quién"
              value={r.person}
              onChange={(person) => set(i, { person })}
              options={[
                { value: "me", label: data.me },
                { value: "other", label: data.other },
              ]}
            />
            <div className="money-pair">
              <DateField label="Desde" value={r.from} onChange={(from) => set(i, { from })} />
              <DateField label="Hasta" value={r.to} onChange={(to) => set(i, { to })} />
            </div>
            <div className="money-pair">
              <TextField label="Neto anual" value={r.salary} inputMode="decimal" onChange={(salary) => set(i, { salary })} invalid={!!r.salary && parseAmount(r.salary) === null} />
              <TextField label="Extra en el tramo" value={r.extra} inputMode="decimal" placeholder="0,00" onChange={(extra) => set(i, { extra })} />
            </div>
            <Button variant="plain" size="small" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              Quitar este tramo
            </Button>
          </div>
        ))}
        <Button icon="plus" size="small" onClick={() => setRows([...rows, { person: "me", from: `${data.year}-01-01`, to: `${data.year}-12-31`, salary: "", extra: "" }])}>
          Añadir un tramo
        </Button>
        <Hint>
          Los tramos cuentan para quien va «A mano», o si Carrera aún no tiene su cifra. El salario anual se prorratea por los días del tramo, y el
          extra se reparte entre ellos, como en Caudal.
        </Hint>
        {error && <Hint tone="warning">{error}</Hint>}
      </div>
    </Sheet>
  );
}
