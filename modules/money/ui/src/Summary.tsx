import {
  AreaTrend,
  Banner,
  Button,
  Card,
  Collapsible,
  EmptyState,
  Hint,
  Icon,
  KeyFigures,
  Notice,
  Panes,
  RingFigure,
  Screen,
  SegmentedControl,
  SeriesChart,
  Skeleton,
  SplitBar,
  numbers,
  useT,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { defaults } from "./analysisState";
import { type Flow, type Kpi, type Spending, type State, type Summary, type Worth, api } from "./api";
import { dayTitle, groupName, moneyWhole, percentText } from "./format";
import { ScreenHeader } from "./Header";
import { basicByMonth, change, cushion, groupHue, lastByGroup, lastYear, thisMonthSpan } from "./summaryParts";

interface Loaded {
  summary: Summary;
  worth: Worth | null;
  spending: Spending | null;
  flow: Flow | null;
}

export function SummaryScreen({ state, onPending }: { state: State; onPending: () => void }) {
  const t = useT();
  const [data, setData] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState(false);
  const [which, setWhich] = useState<"networth" | "liquid">("networth");
  const [liquid, setLiquid] = useState<Worth | null>(null);

  const load = useCallback(() => {
    setFailed(false);
    const year = lastYear();
    const d = defaults();
    const optional = <T,>(promise: Promise<T>) => promise.catch(() => null);
    Promise.all([
      api.summary(),
      optional(api.worth({ ...year, home: false, whole: false })),
      optional(api.spending({ ...year, scope: d.scope, kind: "all" })),
      optional(api.flow({ ...thisMonthSpan(), cycle: false, rent: d.rent })),
    ]).then(
      ([summary, worth, spending, flow]) => setData({ summary, worth, spending, flow }),
      () => setFailed(true),
    );
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    if (which !== "liquid" || liquid) return;
    const accounts = state.accounts.filter((a) => a.liquid !== false && a.asset_class !== "real_estate").map((a) => a.key);
    api.worth({ ...lastYear(), home: false, whole: false, account: accounts }).then(setLiquid, () => undefined);
  }, [which, liquid, state.accounts]);

  const kpi = (key: Kpi["key"]) => data?.summary.kpis.find((k) => k.key === key);
  const waiting = (state.counts.ask ?? 0) + (state.counts.pending ?? 0);

  if (failed) {
    return (
      <Screen label={t("summary.title")}>
        <ScreenHeader title={t("summary.title")} />
        <Notice tone="negative" title={t("summary.failed")} action={{ label: t("common.retry"), onClick: load }} />
      </Screen>
    );
  }
  if (!data) {
    return (
      <Screen label={t("summary.title")}>
        <ScreenHeader title={t("summary.title")} />
        <Skeleton rows={6} label={t("summary.computing")} />
      </Screen>
    );
  }
  if (data.summary.kpis.every((k) => k.value === null)) {
    return (
      <Screen label={t("summary.title")}>
        <ScreenHeader title={t("summary.title")} />
        <EmptyState icon="wallet" title={t("summary.no_data")}>
          {t("summary.no_data_body")}
        </EmptyState>
      </Screen>
    );
  }

  const head = kpi(which);
  const series = which === "liquid" ? liquid : data.worth;
  const carried = head?.carried ?? [];
  const months = data.summary.emergency_months;
  const room = cushion(kpi("emergency"), months);
  const groups = data.worth ? lastByGroup(data.worth) : [];
  const expense = kpi("expense");
  const basic = kpi("basic");
  const bars = data.spending ? basicByMonth(data.spending) : null;
  const ft = data.flow?.totals;
  const emergency = kpi("emergency");
  const cash = kpi("cash");

  const main = (
    <>
      {waiting > 0 && (
        <Banner hue={3} glyph={<Icon name="alert" />}>
          <Button variant="plain" onClick={onPending}>
            {waiting === 1 ? t("summary.to_label_one") : t("summary.to_label_other", { count: waiting })}
          </Button>
        </Banner>
      )}

      <Card>
        <AreaTrend
          label={head?.label ?? t("summary.networth")}
          value={head?.value === null || head?.value === undefined ? "—" : moneyWhole(head.value)}
          delta={head ? change(head.value, head.previous, true) : undefined}
          points={(series?.points ?? []).map((point) => ({ label: point.label, value: point.total }))}
          description={t("summary.trend", { label: head?.label ?? t("summary.networth") })}
          info={t(`summary.info_${which}`)}
          aside={
            <SegmentedControl
              label={t("summary.which")}
              value={which}
              onChange={setWhich}
              options={[
                { value: "networth", label: t("summary.total") },
                { value: "liquid", label: t("summary.liquid") },
              ]}
            />
          }
        >
          {carried.length > 0 && (
            <Collapsible
              title={carried.length === 1 ? t("summary.carried_one") : t("summary.carried_other", { count: carried.length })}
              subtitle={t("summary.carried_sub")}
            >
              {carried.map((one) => (
                <Hint key={one}>{one}</Hint>
              ))}
            </Collapsible>
          )}
        </AreaTrend>
      </Card>

      {ft && ft.income + ft.member > 0 && (
        <Card title={t("summary.this_month")}>
          <SplitBar
            label={t("summary.coming_in")}
            parts={[
              { label: t("summary.spend"), value: moneyWhole(ft.spent + ft.common), share: ft.spent + ft.common, hue: 4 },
              { label: t("summary.invest"), value: moneyWhole(ft.invested), share: ft.invested, hue: 5 },
            ]}
            rest={{ label: ft.left >= 0 ? t("summary.left") : t("summary.from_savings"), value: moneyWhole(ft.left), share: Math.max(0, ft.left) }}
          />
          <KeyFigures
            label={t("summary.month")}
            items={[
              { label: t("summary.in"), value: moneyWhole(ft.income + ft.member), info: t("summary.info_month") },
              ...(ft.rate !== null && Math.abs(ft.rate) <= 1
                ? [{ label: t("summary.rate"), value: percentText(ft.rate), tone: ft.rate >= 0 ? ("positive" as const) : ("negative" as const) }]
                : []),
            ]}
          />
        </Card>
      )}

      <Card title={t("summary.spending")}>
        <KeyFigures
          label={t("summary.spending")}
          items={[expense, basic]
            .filter((k): k is Kpi => Boolean(k))
            .map((k) => {
              const d = change(k.value, k.previous, false, t("summary.against_year"));
              return {
                label: k.label,
                value: k.value === null ? "—" : moneyWhole(k.value),
                foot: d?.text ?? k.detail ?? undefined,
                tone: d?.tone ?? ("neutral" as const),
                info: t(`summary.info_${k.key}`),
              };
            })}
        />
        {bars && bars.labels.length > 1 && (
          <SeriesChart
            kind="stacked"
            label={t("summary.bars")}
            labels={bars.labels}
            series={[
              { key: "basic", name: t("summary.basic"), values: bars.basic },
              { key: "rest", name: t("summary.rest"), values: bars.rest },
            ]}
            order={["basic", "rest"]}
            overlay={expense?.value ? { key: "average", name: t("summary.average"), values: bars.labels.map(() => expense.value!) } : undefined}
            format={(value) => moneyWhole(value)}
          />
        )}
      </Card>
    </>
  );

  const aside = (
    <>
      {emergency && (
        <Card title={t("summary.cushion")}>
          <RingFigure
            size="medium"
            share={room?.share ?? null}
            value={room ? numbers({ maximumFractionDigits: 1 }).format(room.covered) : "—"}
            label={room ? t("summary.of_months", { months }) : t("summary.no_target")}
            detail={
              emergency.value === null
                ? undefined
                : emergency.target
                  ? t("summary.of_amount", { amount: moneyWhole(emergency.value), target: moneyWhole(emergency.target) })
                  : moneyWhole(emergency.value)
            }
            tone={room ? (room.share >= 1 ? "positive" : room.share >= 0.5 ? "info" : "warning") : undefined}
          />
          <KeyFigures
            label={t("summary.the_cushion")}
            items={[{ label: emergency.label, value: emergency.value === null ? "—" : moneyWhole(emergency.value), info: t("summary.info_emergency") }]}
          />
        </Card>
      )}
      {(groups.length > 0 || cash) && (
        <Card title={t("summary.where")}>
          {groups.length > 0 && (
            <SplitBar
              label={t("summary.by_type")}
              parts={groups.map((one) => ({ label: groupName(one.group), value: moneyWhole(one.value), share: one.value, hue: groupHue(one.group) }))}
            />
          )}
          {cash && (
            <KeyFigures label={t("summary.at_hand")} items={[{ label: cash.label, value: cash.value === null ? "—" : moneyWhole(cash.value), info: t("summary.info_cash") }]} />
          )}
        </Card>
      )}
    </>
  );

  return (
    <Screen wide label={t("summary.title")}>
      <ScreenHeader title={t("summary.title")} />
      <Panes main={main} aside={aside} asideLabel={t("summary.aside")} />
      {state.cutoff && (
        <Hint>
          {t("summary.history_hint", { day: dayTitle(state.cutoff) })}
        </Hint>
      )}
    </Screen>
  );
}
