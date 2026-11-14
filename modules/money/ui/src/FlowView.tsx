import { Hint, RingFigure, Sankey, Section, StatRow, StatTile, numbers, useT } from "@openarga/ui";

import { type AnalysisQuery, api } from "./api";
import { Loading, contract, delta, shortDate, signedPercent, useLoad } from "./analysisParts";
import { money, moneyWhole, percentText, say } from "./format";
import { useWide } from "./useWide";

export function FlowView({
  q,
  cycle,
  percent,
  rent,
  againstLabel,
}: {
  q: AnalysisQuery;
  cycle: boolean;
  percent: boolean;
  rent: boolean;
  againstLabel: string;
}) {
  const t = useT();
  const query = { ...q, cycle, rent };
  const wide = useWide();
  const state = useLoad(() => api.flow(query), JSON.stringify(query));

  return (
    <>
      <Loading state={state}>
        {(f) => {
          const tot = f.totals;
          const p = f.previous;
          const spent = tot.spent + tot.common;
          const open = f.segments.some((s) => s.open);
          const rate = tot.rate !== null && Math.abs(tot.rate) <= 1 ? tot.rate : null;
          const cycles = f.segments.filter((s) => s.kind === "cycle");
          const first = f.segments[0];
          const last = f.segments[f.segments.length - 1];
          if (!first || !last || f.links.length === 0) {
            return <Hint>{t("flow.nothing")}</Hint>;
          }
          const base = tot.income + tot.member;
          const before = p ? p.income + p.member : 0;
          const share = percent && base > 0;
          const shown = (now: number, sign = false) => (share ? (sign ? signedPercent(now / base) : percentText(now / base)) : moneyWhole(now, sign));
          const card = (now: number, then: number | null, goodUp: boolean) =>
            share ? points(now / base, then !== null && before > 0 ? then / before : null, againstLabel, goodUp) : tile(now, then, againstLabel, goodUp);
          return (
            <>
              <p className="money-analysis-span">
                {t("flow.span", { from: shortDate(first.from), to: shortDate(last.to) })}
                {open ? t("flow.ongoing") : ""}
                {cycles.length > 0 ? (cycles.length === 1 ? t("flow.cycles_one") : t("flow.cycles_other", { count: cycles.length })) : ""}
              </p>
              <StatRow label={t("flow.title")}>
                <StatTile
                  label={t("flow.in")}
                  value={moneyWhole(tot.income + tot.member)}
                  {...(share ? { foot: t("flow.all") } : tile(tot.income + tot.member, p ? p.income + p.member : null, againstLabel, true))}
                  info={t("flow.info_income")}
                />
                <StatTile
                  label={t("flow.spend")}
                  value={shown(spent)}
                  {...card(spent, p ? p.spent + p.common : null, false)}
                  info={t("flow.info_spent")}
                />
                <StatTile
                  label={t("flow.invest")}
                  value={shown(tot.invested)}
                  {...card(tot.invested, p ? p.invested : null, true)}
                  info={rent ? t("flow.info_invested_rent") : t("flow.info_invested")}
                />
                <StatTile
                  label={tot.left >= 0 ? t("flow.left") : t("flow.from_savings")}
                  value={shown(tot.left, true)}
                  foot={rate !== null ? t("flow.rate", { percent: percentText(rate) }) : undefined}
                  tone={tot.left >= 0 ? "positive" : "negative"}
                  info={t("flow.info_left")}
                />
              </StatRow>
              <Section title={t("flow.where")}>
                {rate !== null && (
                  <RingFigure
                    size="medium"
                    share={Math.max(0, rate)}
                    value={percentText(rate)}
                    label={rate >= 0 ? t("flow.save_of_100", { count: Math.round(rate * 100) }) : t("flow.from_savings")}
                    detail={t("flow.rate_detail")}
                    tone={rate >= 0.2 ? "positive" : rate >= 0 ? "info" : "negative"}
                  />
                )}
                <div className="money-flow">
                  <Sankey
                    label={t("flow.sankey")}
                    nodes={f.nodes}
                    links={f.links}
                    format={(v) => (share ? percentText(v / base) : wide ? money(v, false) : moneyWhole(v))}
                    rowHeight={28}
                    vertical={!wide}
                    share={base > 0 && !share ? (_, value) => percentText(value / base) : undefined}
                  />
                </div>
              </Section>
              {f.unlogged > 0 && (
                <Hint>
                  {f.unlogged === 1 ? t("flow.unlogged_one") : t("flow.unlogged_other", { count: f.unlogged })}
                </Hint>
              )}
              {open && <Hint>{t("flow.open")}</Hint>}
              {cycle && f.payroll && cycles.length > 0 && (
                <Hint>
                  {t("flow.cycle_hint", { day: f.payroll })}
                </Hint>
              )}
              {cycle && f.segments.some((s) => s.kind === "month") && (
                <Hint>
                  {t("flow.history_hint", {
                    moved: f.payroll_moved && f.payroll_moved.in > 0 ? t("flow.moved", { amount: moneyWhole(f.payroll_moved.in) }) : "",
                  })}
                </Hint>
              )}
              {p && rate !== null && p.rate !== null && Math.abs(p.rate) <= 1 && (
                <Hint>
                  {t("flow.rate_against", { now: percentText(rate), then: percentText(p.rate), against: againstLabel, points: pointsText(rate - p.rate) })}
                </Hint>
              )}
            </>
          );
        }}
      </Loading>
    </>
  );
}

function tile(now: number, before: number | null, against: string, goodUp: boolean) {
  const d = delta(now, before, against, goodUp);
  return { foot: d.text, tone: d.tone };
}

function points(now: number, before: number | null, against: string, goodUp: boolean) {
  if (before === null) return { foot: contract(say("delta.no_data", { against })), tone: "neutral" as const };
  const diff = now - before;
  if (Math.abs(diff) < 0.0005) return { foot: say("delta.same", { against }), tone: "neutral" as const };
  return {
    foot: contract(say("flow.points_against", { points: pointsText(diff), against })),
    tone: (goodUp ? diff > 0 : diff < 0) ? ("positive" as const) : ("negative" as const),
  };
}

function pointsText(diff: number): string {
  const value = numbers({ maximumFractionDigits: 1 }).format(Math.abs(diff) * 100);
  return say("flow.points", { value: `${diff > 0 ? "+" : diff < 0 ? "−" : ""}${value}` });
}
