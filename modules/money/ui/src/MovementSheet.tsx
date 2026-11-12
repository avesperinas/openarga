import { Button, ChoiceChips, Collapsible, ConfirmPanel, Hint, Notice, SegmentedControl, SelectField, Sheet, Skeleton, TextField } from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import { api, type Category, type Movement, type MovementDetail, type Payer, Refused, type State } from "./api";
import { NATURE, OWNERSHIP, STATUS, amountText, dayTitle, money, parseAmount, payerLabel, shortDay, subtitle, title } from "./format";

type Mode = "parts" | "settlement" | "return" | "transfer";

interface Draft {
  category: string;
  amount: string;
  payer: Payer | null;
}

const WHY: Partial<Record<Movement["status"], string>> = {
  auto: "Lo decidió una regla, o la clasificación de su banco.",
  default: "Lleva la categoría por defecto de su cuenta. Si no es eso, cámbiala.",
  manual: "Lo etiquetaste tú. Ninguna regla lo cambia.",
  ask: "Es efectivo: dime en qué se fue. Puedes repartirlo en varias categorías.",
  pending: "Ninguna regla lo explica. Dime qué es.",
  transfer: "Dinero entre tus cuentas: no es gasto ni ingreso.",
  return: "Rentabilidad de su cuenta: ni gasto ni ingreso.",
  settlement: "Un pago entre vosotros que salda una parte: ni gasto ni ingreso.",
};

export function MovementSheet({
  id,
  state,
  onClose,
  onChanged,
  onOpen,
  reload,
}: {
  id: string;
  state: State;
  onClose: () => void;
  onChanged: (m: Movement) => void;
  onOpen: (id: string) => void;
  reload: () => void;
}) {
  const [m, setM] = useState<MovementDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [mode, setMode] = useState<Mode>("parts");
  const [transferWith, setTransferWith] = useState("");
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [offer, setOffer] = useState<{ category: string; name: string } | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"save" | "auto" | "merchant" | null>(null);

  useEffect(() => {
    setM(null);
    setEditing(false);
    setOffer(null);
    setDone(null);
    setConfirm(null);
    api.movement(id).then(
      (detail) => {
        setM(detail);
        const editable = !["transfer", "return", "settlement"].includes(detail.status);
        setEditing(editable && (detail.status === "ask" || detail.status === "pending"));
        setMode(detail.status === "settlement" ? "settlement" : detail.status === "return" ? "return" : "parts");
        setTransferWith("");
        setDrafts(
          detail.parts.length
            ? detail.parts.map((p) => ({ category: p.category, amount: amountText(Math.abs(p.amount)), payer: p.payer }))
            : [{ category: "", amount: amountText(Math.abs(detail.amount)), payer: null }],
        );
      },
      () => setFailed(true),
    );
  }, [id]);

  const categories = useMemo(() => sorted(state.categories, m?.amount ?? -1), [state.categories, m?.amount]);
  const byId = useMemo(() => new Map(state.categories.map((c) => [c.id, c])), [state.categories]);
  const total = m ? Math.abs(m.amount) : 0;
  const assigned = drafts.reduce((sum, d) => sum + (parseAmount(d.amount) ?? 0), 0);
  const left = Math.round((total - assigned) * 100) / 100;
  const others = m ? state.accounts.filter((a) => a.key !== m.account).map((a) => ({ value: a.key, label: a.name })) : [];
  const ready =
    mode === "transfer" ? Boolean(transferWith) : mode !== "parts" || (drafts.every((d) => d.category && parseAmount(d.amount)) && left === 0);

  const save = async () => {
    if (!m || !ready) return;
    setSaving(true);
    setError(null);
    try {
      const changed =
        mode === "transfer"
          ? await api.label(m.id, { transfer_with: transferWith })
          : mode === "settlement"
          ? await api.label(m.id, { settlement: true })
          : mode === "return"
            ? await api.label(m.id, { is_return: true })
            : await api.label(m.id, {
                parts: drafts.map((d) => ({
                  amount: String(parseAmount(d.amount)),
                  category: d.category,
                  payer: byId.get(d.category)?.ownership === "shared" ? (d.payer ?? defaultPayer(m, state)) : null,
                })),
              });
      onChanged(changed);
      setM({ ...m, ...changed });
      setEditing(false);
      const only = drafts.length === 1 ? drafts[0] : undefined;
      if (mode === "parts" && only && m.same_merchant > 0) {
        setOffer({ category: only.category, name: byId.get(only.category)?.name ?? "" });
      } else {
        onClose();
      }
    } catch (e) {
      setError(e instanceof Refused ? e.message : "No se ha podido guardar. Inténtalo otra vez.");
    } finally {
      setSaving(false);
    }
  };

  const automatic = async () => {
    if (!m) return;
    setSaving(true);
    try {
      const changed = await api.unlabel(m.id);
      onChanged(changed);
      onClose();
    } catch {
      setError("No se ha podido volver a lo automático.");
    } finally {
      setSaving(false);
    }
  };

  const applyToMerchant = async () => {
    if (!m || !offer) return;
    try {
      const result = await api.merchantRule(m.id, offer.category);
      setDone(`«${offer.name}» para todo lo de ${result.merchant}: ${result.movements} movimientos.`);
      setOffer(null);
      reload();
    } catch {
      setError("No se ha podido crear la regla.");
    }
  };

  const action =
    editing && m && !confirm ? { label: "Guardar", onClick: () => setConfirm("save"), disabled: !ready || saving } : undefined;

  const described = () => {
    if (mode === "transfer") {
      const name = state.accounts.find((a) => a.key === transferWith)?.name ?? "?";
      return `Traspaso ${m && m.amount < 0 ? "a" : "desde"} ${name}`;
    }
    if (mode === "settlement") return "Liquidación entre vosotros";
    if (mode === "return") return "Rentabilidad";
    return drafts
      .map((d) => {
        const cat = byId.get(d.category);
        const payer = cat?.ownership === "shared" && m ? ` · pagó ${payerLabel(d.payer ?? defaultPayer(m, state), state.me, state.other)}` : "";
        return `${cat?.name ?? "?"}${drafts.length > 1 ? ` (${d.amount} €)` : ""}${payer}`;
      })
      .join(", ");
  };

  return (
    <Sheet title={m ? title(m) : "Movimiento"} onClose={onClose} action={action}>
      {failed && <Notice tone="negative" title="No se ha podido abrir" />}
      {!m && !failed && <Skeleton rows={4} label="Cargando el movimiento" />}
      {m && confirm === "save" && (
        <ConfirmPanel
          title="¿Guardar lo que es este movimiento?"
          changes={[
            subtitle(m) === described()
              ? { label: "Qué es", from: `${described()} · ${STATUS[m.status].toLowerCase()}`, to: `${described()} · fijado a mano` }
              : { label: "Qué es", from: m.parts.length || m.status !== "pending" ? subtitle(m) : undefined, to: described() },
          ]}
          detail="Queda fijado: ninguna regla ni sincronización lo cambia. Puedes volver a lo automático cuando quieras."
          action="Guardar cambios"
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            setConfirm(null);
            await save();
          }}
        />
      )}
      {m && confirm === "auto" && (
        <ConfirmPanel
          title="¿Volver a lo automático?"
          changes={[{ label: "Qué es", from: subtitle(m), to: "Lo que digan las reglas" }]}
          detail="Se quita lo que dijiste de este movimiento y vuelve a decidirlo Money."
          action="Volver a lo automático"
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            setConfirm(null);
            await automatic();
          }}
        />
      )}
      {m && confirm === "merchant" && offer && (
        <ConfirmPanel
          title={`¿«${offer.name}» para todo ${m.merchant}?`}
          changes={[{ label: "Movimientos", to: `${m.same_merchant} más, y los que lleguen` }]}
          detail="Se crea una regla para este comercio. Lo que hayas etiquetado a mano no cambia."
          action="Aplicar a todos"
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            setConfirm(null);
            await applyToMerchant();
          }}
        />
      )}
      {m && !confirm && (
        <div className="money-detail">
          <div className="money-hero">
            <span className="money-hero-amount" data-sign={m.kind === "transfer" ? "transfer" : m.amount < 0 ? "out" : "in"}>
              {money(m.amount)}
            </span>
            <span className="money-hero-meta">
              {dayTitle(m.on)} · {m.account_name}
              {m.institution && m.institution !== "—" ? ` · ${m.institution}` : ""}
            </span>
            <span className="money-status" data-status={m.status}>
              {STATUS[m.status]}
            </span>
          </div>

          <Hint>{WHY[m.status]}</Hint>
          {m.before_cutoff && <Hint>Es de antes del corte: ese mes lo cuenta el histórico, no esto.</Hint>}

          {m.transfer && (
            <div className="surface money-transfer">
              <span>
                {m.amount < 0 ? "A" : "Desde"} <strong>{m.transfer.name}</strong>
                {m.transfer.on ? ` · ${shortDay(m.transfer.on)}` : ""}
                {m.transfer.basis === "inferred" ? " · sin extracto de ese lado" : ""}
                {m.transfer.basis === "other_member" ? " · su aportación" : ""}
              </span>
              {m.transfer.fact && (
                <Button variant="plain" size="small" onClick={() => onOpen(m.transfer!.fact!)}>
                  Ver el otro lado
                </Button>
              )}
            </div>
          )}

          {!editing && m.parts.length > 0 && (
            <ul className="money-parts-read">
              {m.parts.map((p, i) => (
                <li key={i}>
                  <span className="money-part-name">
                    {p.category_name}
                    <span className="money-part-kind">
                      {NATURE[p.nature]} · {OWNERSHIP[p.ownership].toLowerCase()}
                      {p.payer ? ` · pagó ${payerLabel(p.payer, state.me, state.other)}` : ""}
                    </span>
                  </span>
                  {m.parts.length > 1 && <span className="money-part-amount">{money(p.amount)}</span>}
                </li>
              ))}
            </ul>
          )}

          {offer && (
            <Notice tone="info" title="¿Lo mismo para todo este comercio?" action={{ label: "Aplicar a todos", onClick: () => setConfirm("merchant") }}>
              Hay {m.same_merchant} movimientos más de {m.merchant}. Puedo poner «{offer.name}» a todos, también a los que
              lleguen. Lo que hayas etiquetado a mano no cambia.
            </Notice>
          )}
          {done && <Notice tone="positive" title="Hecho">{done}</Notice>}

          {editing ? (
            <div className="money-editor">
              <ChoiceChips<Mode>
                label="Qué es"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "parts", label: "Categoría" },
                  { value: "transfer", label: "Traspaso" },
                  { value: "settlement", label: "Liquidación" },
                  { value: "return", label: "Rentabilidad" },
                ]}
              />
              {mode === "transfer" && (
                <>
                  <SelectField<string>
                    label={m.amount < 0 ? "A qué cuenta tuya" : "Desde qué cuenta tuya"}
                    value={transferWith}
                    onChange={setTransferWith}
                    options={[{ value: "", label: "Elige una cuenta" }, ...others]}
                  />
                  <Hint>
                    Dinero entre tus cuentas: ni gasto ni ingreso. Si esa cuenta no tiene este movimiento, Money lo apunta en ella;
                    cuando llegue su extracto, se queda el real.
                  </Hint>
                </>
              )}
              {mode === "parts" && (
                <>
                  {drafts.map((d, i) => {
                    const cat = byId.get(d.category);
                    return (
                      <div key={i} className="surface money-part-edit">
                        <SelectField<string>
                          label={drafts.length > 1 ? `Parte ${i + 1}` : "Categoría"}
                          value={d.category}
                          onChange={(category) => setDrafts(update(drafts, i, { category }))}
                          options={[{ value: "", label: "Elige una categoría" }, ...categories]}
                        />
                        {drafts.length > 1 && (
                          <TextField
                            label="Importe"
                            value={d.amount}
                            inputMode="decimal"
                            onChange={(amount) => setDrafts(update(drafts, i, { amount }))}
                            invalid={!parseAmount(d.amount)}
                          />
                        )}
                        {cat?.ownership === "shared" && (
                          <SegmentedControl<Payer>
                            label="Quién lo pagó"
                            value={d.payer ?? defaultPayer(m, state)}
                            onChange={(payer) => setDrafts(update(drafts, i, { payer }))}
                            options={[
                              { value: "account", label: "Común" },
                              { value: "me", label: state.me },
                              { value: "other", label: state.other },
                            ]}
                          />
                        )}
                        {drafts.length > 1 && (
                          <Button variant="plain" size="small" onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}>
                            Quitar esta parte
                          </Button>
                        )}
                      </div>
                    );
                  })}
                  <div className="money-split">
                    <Button
                      icon="plus"
                      size="small"
                      onClick={() =>
                        setDrafts([
                          ...drafts,
                          { category: "", amount: amountText(Math.max(left, 0)), payer: null },
                        ])
                      }
                    >
                      Repartir en otra parte
                    </Button>
                    {drafts.length > 1 && (
                      <span className="money-left" data-ok={left === 0 || undefined}>
                        {left === 0 ? "Repartido entero" : left > 0 ? `Faltan ${money(left, false)}` : `Sobran ${money(-left, false)}`}
                      </span>
                    )}
                  </div>
                </>
              )}
              {mode === "settlement" && (
                <Hint>Un pago entre vosotros para saldar una parte (devolverle su mitad de algo). No cuenta como gasto.</Hint>
              )}
              {mode === "return" && <Hint>Intereses o rendimiento de la cuenta. No cuenta como ingreso.</Hint>}
              {error && <Hint tone="warning">{error}</Hint>}
              {m.labelled && (
                <Button variant="plain" onClick={() => setConfirm("auto")} disabled={saving}>
                  Volver a lo automático
                </Button>
              )}
            </div>
          ) : (
            <div className="money-actions">
              <Button icon="edit" variant="tinted" onClick={() => setEditing(true)}>
                {m.parts.length ? "Cambiar lo que es" : "Decir qué es"}
              </Button>
              {m.labelled && (
                <Button variant="plain" onClick={() => setConfirm("auto")} disabled={saving}>
                  Volver a lo automático
                </Button>
              )}
            </div>
          )}

          <Collapsible title="Lo que dijo el banco">
            <dl className="money-raw">
              <dt>Texto</dt>
              <dd>{m.text}</dd>
              {m.counterparty && (
                <>
                  <dt>Contraparte</dt>
                  <dd>{m.counterparty}</dd>
                </>
              )}
              {m.counterparty_iban && (
                <>
                  <dt>IBAN de la contraparte</dt>
                  <dd>{m.counterparty_iban}</dd>
                </>
              )}
              {m.bank_category && (
                <>
                  <dt>Clasificación del banco</dt>
                  <dd>{m.bank_category}</dd>
                </>
              )}
              {m.value_on && m.value_on !== m.on && (
                <>
                  <dt>Fecha valor</dt>
                  <dd>{dayTitle(m.value_on)}</dd>
                </>
              )}
              <dt>Fuente</dt>
              <dd>{SOURCE[m.source] ?? m.source}</dd>
            </dl>
          </Collapsible>
        </div>
      )}
    </Sheet>
  );
}

const SOURCE: Record<string, string> = {
  api: "Conexión con el banco",
  statement: "Extracto",
  manual: "Apuntado a mano",
};

function defaultPayer(m: Movement, state: State): Payer {
  if (m.account === "@other") return m.entry?.payer === "me" ? "me" : "other";
  return state.accounts.find((a) => a.key === m.account)?.shared ? "account" : "me";
}

function update(drafts: Draft[], i: number, patch: Partial<Draft>): Draft[] {
  return drafts.map((d, j) => (j === i ? { ...d, ...patch } : d));
}

function sorted(categories: Category[], amount: number): { value: string; label: string }[] {
  const first = amount < 0 ? "expense" : "income";
  return [...categories]
    .sort((a, b) => Number(b.nature === first) - Number(a.nature === first) || a.ownership.localeCompare(b.ownership))
    .map((c) => ({ value: c.id, label: `${c.name} — ${NATURE[c.nature].toLowerCase()} ${OWNERSHIP[c.ownership].toLowerCase()}` }));
}
