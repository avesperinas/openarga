import { Button, ConfirmPanel, DateField, Hint, SegmentedControl, SelectField, Sheet, TextField, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Income, type Person, Refused, type Shared, type Space, api } from "./api";
import { amountText, money, parseAmount, shortDay } from "./format";

const PEOPLE: Person[] = ["me", "other"];

interface Row {
  person: "me" | "other";
  from: string;
  to: string;
  salary: string;
  extra: string;
}

export function IncomesSheet({ data, onClose, onSaved }: { data: Shared; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [rows, setRows] = useState<Row[]>(() =>
    data.incomes.length
      ? data.incomes.map((i) => ({ ...i, salary: amountText(i.salary), extra: i.extra ? amountText(i.extra) : "" }))
      : (["me", "other"] as const).map((person) => ({ person, from: `${data.year}-01-01`, to: `${data.year}-12-31`, salary: "", extra: "" })),
  );
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
      await api.incomes(data.year, incomes);
      onSaved();
    } catch (e) {
      setError(e instanceof Refused ? e.message : t("common.save_failed"));
    }
  };

  const set = (i: number, patch: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const who = (person: "me" | "other") => (person === "me" ? data.me : data.other);
  const spaceName = (id: string) => (id ? (spaces.find((s) => s.id === id)?.name ?? t("incomes.a_space")) : t("incomes.none"));
  const before = (person: "me" | "other") =>
    data.incomes.filter((i) => i.person === person).map((i) => `${money(i.salary, false)} (${shortDay(i.from)}–${shortDay(i.to)})`).join(", ") || t("incomes.nothing");
  const after = (person: "me" | "other") =>
    filled.filter((r) => r.person === person).map((r) => `${money(parseAmount(r.salary) ?? 0, false)} (${shortDay(r.from)}–${shortDay(r.to)})`).join(", ") || t("incomes.nothing");

  if (confirming) {
    return (
      <Sheet title={t("incomes.title", { year: data.year })} onClose={onClose}>
        <ConfirmPanel
          title={t("incomes.confirm")}
          changes={[
            ...((data.space_id ?? "") !== space
              ? [{ label: t("incomes.space"), from: spaceName(data.space_id ?? ""), to: spaceName(space) }]
              : []),
            ...PEOPLE.map((p) => ({ label: t("incomes.ranges_of", { who: who(p) }), from: before(p), to: after(p) })),
          ]}
          detail={t("incomes.detail")}
          action={t("incomes.save")}
          onCancel={() => setConfirming(false)}
          onConfirm={save}
        />
      </Sheet>
    );
  }

  return (
    <Sheet title={t("incomes.title", { year: data.year })} onClose={onClose} action={{ label: t("common.save"), onClick: () => setConfirming(true), disabled: !valid }}>
      <div className="money-form">
        {spaces.length > 0 && (
          <>
            <SelectField<string>
              label={t("incomes.space")}
              value={space}
              onChange={setSpace}
              options={[{ value: "", label: t("incomes.none") }, ...spaces.map((s) => ({ value: s.id, label: s.name }))]}
            />
            <Hint>{t("incomes.space_hint")}</Hint>
          </>
        )}
        {rows.map((r, i) => (
          <div key={i} className="surface money-part-edit">
            <SegmentedControl<"me" | "other">
              label={t("incomes.whose")}
              value={r.person}
              onChange={(person) => set(i, { person })}
              options={[
                { value: "me", label: data.me },
                { value: "other", label: data.other },
              ]}
            />
            <div className="money-pair">
              <DateField label={t("incomes.from")} value={r.from} onChange={(from) => set(i, { from })} />
              <DateField label={t("incomes.to")} value={r.to} onChange={(to) => set(i, { to })} />
            </div>
            <div className="money-pair">
              <TextField label={t("incomes.net")} value={r.salary} inputMode="decimal" onChange={(salary) => set(i, { salary })} invalid={!!r.salary && parseAmount(r.salary) === null} />
              <TextField label={t("incomes.extra")} value={r.extra} inputMode="decimal" placeholder={amountText(0)} onChange={(extra) => set(i, { extra })} />
            </div>
            <Button variant="plain" size="small" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              {t("incomes.remove")}
            </Button>
          </div>
        ))}
        <Button icon="plus" size="small" onClick={() => setRows([...rows, { person: "me", from: `${data.year}-01-01`, to: `${data.year}-12-31`, salary: "", extra: "" }])}>
          {t("incomes.add")}
        </Button>
        <Hint>
          {t("incomes.hint")}
        </Hint>
        {error && <Hint tone="warning">{error}</Hint>}
      </div>
    </Sheet>
  );
}
