import { Button, ChoiceChips, Collapsible, ConfirmPanel, Hint, Notice, SegmentedControl, SelectField, Sheet, Skeleton, TextField, useT } from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import { api, type Category, type Movement, type MovementDetail, type Payer, Refused, type State } from "./api";
import { currencySymbol, natureName, ownershipName, statusName, amountText, dayTitle, money, parseAmount, payerLabel, shortDay, subtitle, title } from "./format";

type Mode = "parts" | "settlement" | "return" | "transfer";

interface Draft {
  category: string;
  amount: string;
  payer: Payer | null;
}

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
  const t = useT();
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
      setError(e instanceof Refused ? e.message : t("sheet.save_failed"));
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
      setError(t("sheet.auto_failed"));
    } finally {
      setSaving(false);
    }
  };

  const applyToMerchant = async () => {
    if (!m || !offer) return;
    try {
      const result = await api.merchantRule(m.id, offer.category);
      setDone(t("sheet.rule_done", { name: offer.name, merchant: result.merchant, count: result.movements }));
      setOffer(null);
      reload();
    } catch {
      setError(t("sheet.rule_failed"));
    }
  };

  const action =
    editing && m && !confirm ? { label: t("common.save"), onClick: () => setConfirm("save"), disabled: !ready || saving } : undefined;

  const described = () => {
    if (mode === "transfer") {
      const name = state.accounts.find((a) => a.key === transferWith)?.name ?? "?";
      return t(m && m.amount < 0 ? "sheet.transfer_to" : "sheet.transfer_from", { name });
    }
    if (mode === "settlement") return t("movement.settlement");
    if (mode === "return") return statusName("return");
    return drafts
      .map((d) => {
        const cat = byId.get(d.category);
        const payer = cat?.ownership === "shared" && m ? t("sheet.paid", { payer: payerLabel(d.payer ?? defaultPayer(m, state), state.me, state.other) }) : "";
        return `${cat?.name ?? "?"}${drafts.length > 1 ? ` (${d.amount} ${currencySymbol()})` : ""}${payer}`;
      })
      .join(", ");
  };

  return (
    <Sheet title={m ? title(m) : t("sheet.movement")} onClose={onClose} action={action}>
      {failed && <Notice tone="negative" title={t("sheet.open_failed")} />}
      {!m && !failed && <Skeleton rows={4} label={t("sheet.loading")} />}
      {m && confirm === "save" && (
        <ConfirmPanel
          title={t("sheet.confirm_save")}
          changes={[
            subtitle(m) === described()
              ? { label: t("sheet.what"), from: `${described()} · ${statusName(m.status).toLowerCase()}`, to: t("sheet.fixed", { what: described() }) }
              : { label: t("sheet.what"), from: m.parts.length || m.status !== "pending" ? subtitle(m) : undefined, to: described() },
          ]}
          detail={t("sheet.fixed_detail")}
          action={t("sheet.save_changes")}
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            setConfirm(null);
            await save();
          }}
        />
      )}
      {m && confirm === "auto" && (
        <ConfirmPanel
          title={t("sheet.confirm_auto")}
          changes={[{ label: t("sheet.what"), from: subtitle(m), to: t("sheet.rules_say") }]}
          detail={t("sheet.auto_detail")}
          action={t("sheet.back_auto")}
          onCancel={() => setConfirm(null)}
          onConfirm={async () => {
            setConfirm(null);
            await automatic();
          }}
        />
      )}
      {m && confirm === "merchant" && offer && (
        <ConfirmPanel
          title={t("sheet.confirm_merchant", { name: offer.name, merchant: m.merchant })}
          changes={[{ label: t("sheet.movements"), to: t("sheet.more_coming", { count: m.same_merchant }) }]}
          detail={t("sheet.merchant_detail")}
          action={t("sheet.apply_all")}
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
              {statusName(m.status)}
            </span>
          </div>

          {WHY_KEYS.has(m.status) && <Hint>{t(`why.${m.status}`)}</Hint>}
          {m.before_cutoff && <Hint>{t("sheet.before_cutoff")}</Hint>}

          {m.transfer && (
            <div className="surface money-transfer">
              <span>
                {m.amount < 0 ? t("sheet.to") : t("sheet.from")} <strong>{m.transfer.name}</strong>
                {m.transfer.on ? ` · ${shortDay(m.transfer.on)}` : ""}
                {m.transfer.basis === "inferred" ? t("sheet.inferred") : ""}
                {m.transfer.basis === "other_member" ? t("sheet.their_contribution") : ""}
              </span>
              {m.transfer.fact && (
                <Button variant="plain" size="small" onClick={() => onOpen(m.transfer!.fact!)}>
                  {t("sheet.other_side")}
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
                      {natureName(p.nature)} · {ownershipName(p.ownership).toLowerCase()}
                      {p.payer ? t("sheet.paid", { payer: payerLabel(p.payer, state.me, state.other) }) : ""}
                    </span>
                  </span>
                  {m.parts.length > 1 && <span className="money-part-amount">{money(p.amount)}</span>}
                </li>
              ))}
            </ul>
          )}

          {offer && (
            <Notice tone="info" title={t("sheet.same_merchant")} action={{ label: t("sheet.apply_all"), onClick: () => setConfirm("merchant") }}>
              {t("sheet.same_merchant_body", { count: m.same_merchant, merchant: m.merchant, name: offer.name })}
            </Notice>
          )}
          {done && <Notice tone="positive" title={t("sheet.done")}>{done}</Notice>}

          {editing ? (
            <div className="money-editor">
              <ChoiceChips<Mode>
                label={t("sheet.what")}
                value={mode}
                onChange={setMode}
                options={[
                  { value: "parts", label: t("sheet.category") },
                  { value: "transfer", label: statusName("transfer") },
                  { value: "settlement", label: statusName("settlement") },
                  { value: "return", label: statusName("return") },
                ]}
              />
              {mode === "transfer" && (
                <>
                  <SelectField<string>
                    label={m.amount < 0 ? t("sheet.to_account") : t("sheet.from_account")}
                    value={transferWith}
                    onChange={setTransferWith}
                    options={[{ value: "", label: t("sheet.pick_account") }, ...others]}
                  />
                  <Hint>
                    {t("sheet.transfer_hint")}
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
                          label={drafts.length > 1 ? t("sheet.part", { n: i + 1 }) : t("sheet.category")}
                          value={d.category}
                          onChange={(category) => setDrafts(update(drafts, i, { category }))}
                          options={[{ value: "", label: t("sheet.pick_category") }, ...categories]}
                        />
                        {drafts.length > 1 && (
                          <TextField
                            label={t("sheet.amount")}
                            value={d.amount}
                            inputMode="decimal"
                            onChange={(amount) => setDrafts(update(drafts, i, { amount }))}
                            invalid={!parseAmount(d.amount)}
                          />
                        )}
                        {cat?.ownership === "shared" && (
                          <SegmentedControl<Payer>
                            label={t("sheet.who_paid")}
                            value={d.payer ?? defaultPayer(m, state)}
                            onChange={(payer) => setDrafts(update(drafts, i, { payer }))}
                            options={[
                              { value: "account", label: t("sheet.shared_account") },
                              { value: "me", label: state.me },
                              { value: "other", label: state.other },
                            ]}
                          />
                        )}
                        {drafts.length > 1 && (
                          <Button variant="plain" size="small" onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}>
                            {t("sheet.remove_part")}
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
                      {t("sheet.add_part")}
                    </Button>
                    {drafts.length > 1 && (
                      <span className="money-left" data-ok={left === 0 || undefined}>
                        {left === 0 ? t("sheet.all_split") : left > 0 ? t("sheet.missing", { amount: money(left, false) }) : t("sheet.extra", { amount: money(-left, false) })}
                      </span>
                    )}
                  </div>
                </>
              )}
              {mode === "settlement" && (
                <Hint>{t("sheet.settlement_hint")}</Hint>
              )}
              {mode === "return" && <Hint>{t("sheet.return_hint")}</Hint>}
              {error && <Hint tone="warning">{error}</Hint>}
              {m.labelled && (
                <Button variant="plain" onClick={() => setConfirm("auto")} disabled={saving}>
                  {t("sheet.back_auto")}
                </Button>
              )}
            </div>
          ) : (
            <div className="money-actions">
              <Button icon="edit" variant="tinted" onClick={() => setEditing(true)}>
                {m.parts.length ? t("sheet.change") : t("sheet.say")}
              </Button>
              {m.labelled && (
                <Button variant="plain" onClick={() => setConfirm("auto")} disabled={saving}>
                  {t("sheet.back_auto")}
                </Button>
              )}
            </div>
          )}

          <Collapsible title={t("sheet.bank_said")}>
            <dl className="money-raw">
              <dt>{t("sheet.text")}</dt>
              <dd>{m.text}</dd>
              {m.counterparty && (
                <>
                  <dt>{t("sheet.counterparty")}</dt>
                  <dd>{m.counterparty}</dd>
                </>
              )}
              {m.counterparty_iban && (
                <>
                  <dt>{t("sheet.counterparty_iban")}</dt>
                  <dd>{m.counterparty_iban}</dd>
                </>
              )}
              {m.bank_category && (
                <>
                  <dt>{t("sheet.bank_category")}</dt>
                  <dd>{m.bank_category}</dd>
                </>
              )}
              {m.value_on && m.value_on !== m.on && (
                <>
                  <dt>{t("sheet.value_date")}</dt>
                  <dd>{dayTitle(m.value_on)}</dd>
                </>
              )}
              <dt>{t("sheet.source")}</dt>
              <dd>{SOURCES.has(m.source) ? t(`source.${m.source}`) : m.source}</dd>
            </dl>
          </Collapsible>
        </div>
      )}
    </Sheet>
  );
}

const SOURCES = new Set(["api", "statement", "manual"]);
const WHY_KEYS = new Set(["auto", "default", "manual", "ask", "pending", "transfer", "return", "settlement"]);

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
    .map((c) => ({ value: c.id, label: `${c.name} — ${natureName(c.nature).toLowerCase()} ${ownershipName(c.ownership).toLowerCase()}` }));
}
