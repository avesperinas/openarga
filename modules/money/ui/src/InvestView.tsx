import {
  DataTable,
  Hint,
  GainChart,
  Section,
  SelectField,
  SeriesChart,
  StatRow,
  StatTile,
  type TableColumn,
  useT,
} from "@openarga/ui";
import { useState } from "react";

import { type AnalysisQuery, type Product, api } from "./api";
import { CsvButton, Loading, RowSheet, dayText, narrowColumns, signedPercent, useLoad } from "./analysisParts";
import { CompositionSection } from "./Composition";
import { axisMonth, crossesYears } from "./analysisState";
import { money, moneyWhole } from "./format";
import { useWide } from "./useWide";

const ALL = "__all__";

export function InvestView({ q, other }: { q: AnalysisQuery; other: string }) {
  const t = useT();
  const key = JSON.stringify(q);
  const state = useLoad(() => api.investments(q), key);
  const [picked, setPicked] = useState<string>(ALL);
  const [open, setOpen] = useState<Product | null>(null);
  const wide = useWide();

  return (
    <Loading state={state}>
      {(inv) => {
        const sum = inv.total;
        if (inv.rows.length === 0)
          return (
            <Hint>
              {q.group?.length || q.account?.length
                ? t("invest.no_product")
                : t("invest.none")}
            </Hint>
          );
        const product = inv.rows.find((r) => r.key === picked);
        const series = product ? product.series : sumSeries(inv.rows);
        const years = crossesYears(series.map((p) => p.label));
        const contribYears = crossesYears(inv.contributions.labels);
        const withOther = inv.rows.filter((r) => r.capital_other);
        const columns: TableColumn<Product>[] = [
          { key: "name", label: t("invest.product"), cell: (r) => (r.carried || r.estimated ? `${r.name} ·` : r.name), csv: (r) => r.name },
          { key: "capital", label: t("invest.contributed"), numeric: true, cell: (r) => money(r.capital, false), csv: (r) => r.capital },
          { key: "value", label: t("invest.value"), numeric: true, cell: (r) => money(r.value, false), csv: (r) => r.value },
          { key: "gain", label: t("invest.gain"), numeric: true, cell: (r) => money(r.gain), csv: (r) => r.gain },
          { key: "simple", label: t("invest.simple"), numeric: true, cell: (r) => signedPercent(r.simple), csv: (r) => r.simple },
          { key: "xirr", label: t("invest.xirr"), numeric: true, cell: (r) => signedPercent(r.xirr), csv: (r) => r.xirr },
          {
            key: "period",
            label: t("invest.in_period"),
            numeric: true,
            cell: (r) => `${money(r.period_gain)} · ${signedPercent(r.period_return)}`,
            csv: (r) => r.period_gain,
          },
          {
            key: "in",
            label: t("invest.contributed_in_period"),
            numeric: true,
            cell: (r) => money(r.contributed_in_period, false),
            csv: (r) => r.contributed_in_period,
          },
        ];
        const valueChart = (
          <Section title={t("invest.value_vs")}>
            <SelectField
              label={t("invest.product")}
              value={product ? picked : ALL}
              onChange={setPicked}
              options={[{ value: ALL, label: t("invest.all") }, ...inv.rows.map((r) => ({ value: r.key, label: r.name }))]}
            />
            <GainChart
              label={t("invest.chart", { what: product ? product.name : t("invest.all_products") })}
              labels={series.map((p) => axisMonth(p.label, years))}
              value={series.map((p) => p.value)}
              contributed={series.map((p) => p.capital)}
              format={(v) => money(v, false)}
            />
            {inv.widened && <Hint>{t("invest.widened")}</Hint>}
          </Section>
        );
        const contributions = (
          <>
            {inv.contributions.series.length > 0 && (
              <Section title={t("invest.by_month")}>
                <SeriesChart
                  label={t("invest.by_month_chart")}
                  kind="stacked"
                  labels={inv.contributions.labels.map((l) => axisMonth(l, contribYears))}
                  series={inv.contributions.series}
                  order={inv.rows.map((r) => r.key)}
                  format={(v) => money(v, false)}
                  axisFormat={(v) => moneyWhole(v)}
                />
              </Section>
            )}
          </>
        );
        const composition = <CompositionSection q={q} picked={product ? picked : null} />;
        return (
          <>
            <StatRow label={t("invest.title")}>
              <StatTile
                label={t("invest.value")}
                value={moneyWhole(sum.value)}
                foot={t("invest.contributed_amount", { amount: moneyWhole(sum.capital) })}
                info={t("invest.info_value")}
              />
              <StatTile
                label={t("invest.gain")}
                value={moneyWhole(sum.gain, true)}
                foot={t("invest.over_contributed", { percent: signedPercent(sum.simple) })}
                tone={sum.gain >= 0 ? "positive" : "negative"}
                info={t("invest.info_gain")}
              />
              <StatTile
                label={t("invest.xirr")}
                value={signedPercent(sum.xirr)}
                foot={t("invest.with_dates")}
                tone={sum.xirr === null ? "neutral" : sum.xirr >= 0 ? "positive" : "negative"}
                info={t("invest.info_xirr")}
              />
              <StatTile
                label={t("invest.in_period")}
                value={moneyWhole(sum.period_gain, true)}
                foot={t("invest.period_foot", { percent: signedPercent(sum.period_return), amount: moneyWhole(sum.contributed_in_period) })}
                tone={sum.period_gain >= 0 ? "positive" : "negative"}
                info={t("invest.info_period")}
              />
            </StatRow>

            {valueChart}

            <Section title={t("invest.returns")}>
              <DataTable
                label={t("invest.returns")}
                columns={wide ? columns : narrowColumns(columns, ["name", "value", "xirr"])}
                rows={inv.rows}
                rowKey={(r) => r.key}
                onRowClick={(r) => {
                  setPicked(r.key);
                  if (!wide) setOpen(r);
                }}
                footer={
                  wide
                    ? [
                        t("common.total"),
                        money(sum.capital, false),
                        money(sum.value, false),
                        money(sum.gain),
                        signedPercent(sum.simple),
                        signedPercent(sum.xirr),
                        `${money(sum.period_gain)} · ${signedPercent(sum.period_return)}`,
                        money(sum.contributed_in_period, false),
                      ]
                    : [t("common.total"), money(sum.value, false), signedPercent(sum.xirr)]
                }
              />
              <CsvButton name={`${t("invest.csv")}-${inv.on}`} columns={columns} rows={inv.rows} />
              {inv.rows.some((r) => r.estimated) && (
                <Hint>
                  {t("invest.estimated", { day: dayText(inv.rows.map((r) => r.estimated ?? "").sort().slice(-1)[0] ?? "") })}
                </Hint>
              )}
              {inv.rows.some((r) => r.carried) && (
                <Hint>{t("invest.carried")}</Hint>
              )}
              {withOther.map((r) => (
                <Hint key={r.key}>
                  {t("invest.other", { name: r.name, other, amount: moneyWhole(r.capital_other ?? 0) })}
                </Hint>
              ))}
            </Section>

            {composition}
            {contributions}
            {open && (
              <RowSheet title={open.name} columns={columns} row={open} onClose={() => setOpen(null)} />
            )}
          </>
        );
      }}
    </Loading>
  );
}

function sumSeries(rows: Product[]) {
  const first = rows[0]?.series ?? [];
  return first.map((point, index) => ({
    label: point.label,
    value: rows.reduce((sum, r) => sum + (r.series[index]?.value ?? 0), 0),
    capital: rows.reduce((sum, r) => sum + (r.series[index]?.capital ?? 0), 0),
  }));
}
