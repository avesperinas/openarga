import { Button, DateField, Hint, List, ListRow, Section, Sheet, TextField, useT } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type PositionRow, type PositionsCard, Refused, type ProductDetail, api } from "./api";
import { capital, decimalMark, isoDay, money, percentText, shortDay } from "./format";
import { EMPTY_DRAFT, type PositionDraft, bodyOf, draftOf, looksLikeIsin, symbolOf } from "./positionsForm";

function problemOf(t: ReturnType<typeof useT>, e: unknown): string {
  return e instanceof Refused ? capital(e.message) : t("common.save_failed");
}

function priceLine(t: ReturnType<typeof useT>, row: PositionRow): string {
  if (row.price_source === "cost") return t("positions.priced_cost");
  return t(row.price_source === "hub" ? "positions.priced_hub" : "positions.priced_manual", { price: money(row.price, false), day: shortDay(row.price_on) });
}

export function PositionsSheet({ product, onBack, onChanged }: { product: ProductDetail; onBack: () => void; onChanged: () => void }) {
  const t = useT();
  const [card, setCard] = useState<PositionsCard | null>(null);
  const [editing, setEditing] = useState<PositionDraft | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.positions(product.key).then(setCard, () => setProblem(t("positions.open_failed")));
  }, [product.key]);

  const today = isoDay(new Date());
  const mark = decimalMark();

  const leave = () => {
    setEditing(null);
    setProblem(null);
  };

  const save = async () => {
    if (!editing) return;
    const body = bodyOf(editing, mark, today);
    if (!body) return;
    setBusy(true);
    try {
      setCard(await api.setPosition(product.key, body));
      onChanged();
      leave();
    } catch (e) {
      setProblem(problemOf(t, e));
    }
    setBusy(false);
  };

  const remove = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      setCard(await api.removePosition(product.key, symbolOf(editing.symbol)));
      onChanged();
      leave();
    } catch (e) {
      setProblem(problemOf(t, e));
    }
    setBusy(false);
  };

  if (editing) {
    const existing = card?.positions.some((p) => p.symbol === symbolOf(editing.symbol)) ?? false;
    const body = bodyOf(editing, mark, today);
    const set = (change: Partial<PositionDraft>) => setEditing({ ...editing, ...change });
    const symbol = symbolOf(editing.symbol);
    return (
      <Sheet
        title={existing ? t("positions.edit") : t("positions.add")}
        onClose={leave}
        action={{ label: t("common.save"), onClick: save, disabled: !body || busy }}
      >
        {problem && <Hint tone="warning">{problem}</Hint>}
        <TextField label={t("positions.symbol")} value={editing.symbol} onChange={(value) => set({ symbol: value })} placeholder="IE00B4L5Y983" invalid={editing.symbol !== "" && !symbol} />
        <Hint>{symbol && !looksLikeIsin(symbol) ? t("positions.ticker_hint") : t("positions.symbol_hint")}</Hint>
        <TextField label={t("positions.name")} value={editing.name} onChange={(value) => set({ name: value })} />
        <TextField label={t("positions.units")} value={editing.units} onChange={(value) => set({ units: value })} inputMode="decimal" />
        <TextField label={t("positions.cost")} value={editing.cost} onChange={(value) => set({ cost: value })} inputMode="decimal" />
        <Hint>{t("positions.cost_hint")}</Hint>
        <Section title={t("positions.by_hand")}>
          <Hint>{t("positions.by_hand_hint")}</Hint>
          <TextField label={t("positions.price")} value={editing.price} onChange={(value) => set({ price: value })} inputMode="decimal" />
          <DateField label={t("positions.price_on")} value={editing.priceOn} onChange={(value) => set({ priceOn: value })} max={today} />
        </Section>
        {existing && (
          <Button variant="destructive" size="small" onClick={remove} disabled={busy}>
            {t("positions.remove")}
          </Button>
        )}
      </Sheet>
    );
  }

  return (
    <Sheet title={t("positions.title", { name: product.name })} onClose={onBack}>
      {problem && <Hint tone="warning">{problem}</Hint>}
      {!card && !problem && <Hint>{t("positions.loading")}</Hint>}
      {card && (
        <>
          <Hint>{t("positions.hint")}</Hint>
          {card.positions.length === 0 ? (
            <Hint>{t("positions.none")}</Hint>
          ) : (
            <>
              <List>
                {card.positions.map((row) => (
                  <ListRow
                    key={row.symbol}
                    title={row.name || row.symbol}
                    subtitle={`${t("positions.units_at", { units: row.units })} · ${priceLine(t, row)}`}
                    value={money(row.value, false)}
                    detail={`${money(row.gain)}${row.gain_pct === null ? "" : ` · ${percentText(row.gain_pct / 100)}`}`}
                    tone={row.gain < 0 ? "negative" : "positive"}
                    onClick={() => setEditing(draftOf(row))}
                  />
                ))}
              </List>
              <List>
                <ListRow title={t("positions.cost_total")} value={money(card.cost, false)} />
                <ListRow title={t("positions.value_total")} value={money(card.value, false)} />
                <ListRow title={t("positions.gain_total")} value={money(card.gain)} />
              </List>
            </>
          )}
          <Button variant="tinted" size="small" onClick={() => setEditing({ ...EMPTY_DRAFT })}>
            {t("positions.add")}
          </Button>
        </>
      )}
    </Sheet>
  );
}
