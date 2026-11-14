import {
  DataTable,
  Heading,
  Hint,
  Section,
  SegmentedControl,
  SeriesChart,
  ShareChart,
  StatRow,
  StatTile,
  type TableColumn,
  useT,
} from "@openarga/ui";
import { useState } from "react";

import { type AnalysisQuery, type WorthRow, api } from "./api";
import { CsvButton, Loading, RowSheet, dayText, delta, narrowColumns, signedPercent, useLoad } from "./analysisParts";
import { axisMonth, crossesYears } from "./analysisState";
import { groupName, money, moneyWhole, percentText } from "./format";
import { useWide } from "./useWide";

type By = "group" | "institution" | "account";

export function WorthView({ q, home }: { q: AnalysisQuery; home: boolean }) {
  const t = useT();
  const key = JSON.stringify(q);
  const state = useLoad(() => api.worth(q), key);
  const [by, setBy] = useState<By>("group");
  const [open, setOpen] = useState<WorthRow | null>(null);
  const wide = useWide();

  return (
    <Loading state={state}>
      {(w) => {
        if (w.rows.length === 0 && (q.group?.length || q.account?.length)) return <Hint>{t("worth.no_account")}</Hint>;
        const growth = w.contributed !== null ? w.total - w.contributed : null;
        const change = delta(w.total, w.previous, t("delta.the_day", { day: dayText(w.before) }));
        const years = crossesYears(w.points.map((p) => p.label));
        const carried = w.rows.filter((r) => r.carried);
        const estimated = w.rows.filter((r) => r.estimated);
        const shares = shareBy(w.rows, by).map((one) => (by === "group" ? { ...one, name: groupName(one.key) } : one));
        const columns: TableColumn<WorthRow>[] = [
          { key: "name", label: t("worth.account"), cell: (r) => (r.carried || r.estimated ? `${r.name} ·` : r.name), csv: (r) => r.name },
          { key: "institution", label: t("worth.institution"), cell: (r) => r.institution },
          { key: "group", label: t("worth.type"), cell: (r) => groupName(r.group) },
          { key: "value", label: t("worth.value"), numeric: true, cell: (r) => money(r.value, false), csv: (r) => r.value },
          {
            key: "change",
            label: t("worth.change"),
            numeric: true,
            cell: (r) => (r.previous === null ? "—" : money(r.value - r.previous)),
            csv: (r) => (r.previous === null ? null : Math.round((r.value - r.previous) * 100) / 100),
          },
          {
            key: "pct",
            label: "%",
            numeric: true,
            cell: (r) => (r.previous ? signedPercent((r.value - r.previous) / Math.abs(r.previous)) : "—"),
            csv: (r) => (r.previous ? Math.round(((r.value - r.previous) / Math.abs(r.previous)) * 10000) / 10000 : null),
          },
        ];
        const firstPoint = w.points[0];
        const steps = Math.max(1, w.points.length - 1);
        const monthly = firstPoint && w.points.length > 1 ? (w.total - firstPoint.total) / steps : null;
        return (
          <>
            {monthly !== null && Math.abs(monthly) >= 1 && (
              <Heading>
                {monthly > 0
                  ? t("worth.up", { amount: moneyWhole(monthly) })
                  : t("worth.down", { amount: moneyWhole(-monthly) })}
              </Heading>
            )}
            <StatRow label={t("worth.title")}>
              <StatTile label={t("worth.title")} value={moneyWhole(w.total)} foot={change.text} tone={change.tone} info={t("worth.info_total")} />
              {w.contributed !== null && (
                <StatTile label={t("worth.contributed")} value={moneyWhole(w.contributed)} foot={t("worth.contributed_foot")} info={t("worth.info_contributed")} />
              )}
              {growth !== null && (
                <StatTile
                  label={t("worth.growth")}
                  value={moneyWhole(growth, true)}
                  foot={w.contributed ? t("worth.over_contributed", { percent: signedPercent(growth / w.contributed) }) : undefined}
                  tone={growth >= 0 ? "positive" : "negative"}
                  info={t("worth.info_growth")}
                />
              )}
            </StatRow>

            <Section title={t("worth.evolution")}>
              <SeriesChart
                label={t("worth.chart")}
                kind="area"
                labels={w.points.map((p) => axisMonth(p.label, years))}
                series={w.groups.map((g) => ({ key: g, name: groupName(g), values: w.points.map((p) => p.by_group[g] ?? 0) }))}
                order={w.groups}
                overlay={{ key: "contributed", name: t("worth.contributed"), values: w.points.map((p) => p.contributed) }}
                format={(v) => money(v, false)}
                axisFormat={(v) => moneyWhole(v)}
              />
              {w.widened && <Hint>{t("worth.widened")}</Hint>}
            </Section>

            <Section title={t("worth.split_on", { day: dayText(w.on) })}>
              <div className="money-split">
                <div className="money-split-side">
                  <SegmentedControl
                    label={t("worth.group_by")}
                    value={by}
                    onChange={setBy}
                    options={[
                      { value: "group", label: t("worth.type") },
                      { value: "institution", label: t("worth.institution") },
                      { value: "account", label: t("worth.account") },
                    ]}
                  />
                  <ShareChart
                    label={t("worth.split")}
                    items={shares}
                    order={by === "group" ? w.groups : undefined}
                    format={(v) => moneyWhole(v)}
                    center={moneyWhole(w.total)}
                  />
                </div>
                <DataTable
                  label={t("worth.table")}
                  columns={wide ? columns : narrowColumns(columns, ["name", "value"])}
                  rows={w.rows}
                  rowKey={(r) => r.key}
                  onRowClick={wide ? undefined : setOpen}
                  footer={
                    wide
                      ? [t("common.total"), "", "", money(w.total, false), w.previous !== null ? money(w.total - w.previous) : "", ""]
                      : [t("common.total"), money(w.total, false)]
                  }
                />
              </div>
              <CsvButton name={`${t("worth.csv")}-${w.on}`} columns={columns} rows={w.rows} />
              {carried.length > 0 && (
                <Hint>
                  {t("worth.carried")}{" "}
                  {carried.map((r) => `${r.name} (${r.since ? dayText(r.since) : "—"})`).join(", ")}.
                </Hint>
              )}
              {estimated.length > 0 && (
                <Hint>
                  {t("worth.estimated")}{" "}
                  {estimated.map((r) => `${r.name} (${t("worth.as_of", { day: r.estimated ? dayText(r.estimated) : "—" })})`).join(", ")}.{" "}
                  {t("worth.estimated_end")}
                </Hint>
              )}
              {!home && <Hint>{t("worth.no_home")}</Hint>}
              {open && <RowSheet title={open.name} columns={columns} row={open} onClose={() => setOpen(null)} />}
              {w.contributed !== null && w.total > 0 && (
                <Hint>
                  {t("worth.of_every_100", { mine: Math.round((w.contributed / w.total) * 100) })}
                  {growth !== null && growth > 0 ? t("worth.and_growth", { percent: percentText(growth / w.total) }) : "."}
                </Hint>
              )}
            </Section>
          </>
        );
      }}
    </Loading>
  );
}

function shareBy(rows: WorthRow[], by: By) {
  const sums = new Map<string, number>();
  for (const r of rows) {
    const key = by === "group" ? r.group : by === "institution" ? r.institution : r.name;
    sums.set(key, (sums.get(key) ?? 0) + r.value);
  }
  return [...sums.entries()].filter(([, v]) => v > 0).map(([k, v]) => ({ key: k, name: k, value: v }));
}
