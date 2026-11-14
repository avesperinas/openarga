import {
  DataTable,
  GroupLabel,
  Heading,
  Hint,
  List,
  ListRow,
  Section,
  SeriesChart,
  Sheet,
  Skeleton,
  StatRow,
  StatTile,
  type TableColumn,
  Treemap,
  useT,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { type AnalysisQuery, type CategoryDetail, type SpendingRow, type State, api } from "./api";
import { CsvButton, Loading, dayText, delta, shortDate, signedPercent, useLoad } from "./analysisParts";
import { type Basic, type Scope, axisMonth, crossesYears } from "./analysisState";
import { money, moneyWhole, percentText, say } from "./format";
import { useWide } from "./useWide";

export function spendingLead(rows: SpendingRow[]): string | null {
  const growing = rows
    .filter((r) => r.average !== null && r.usual > 0 && r.total > 0)
    .map((r) => ({ r, by: (r.average as number) / r.usual - 1 }))
    .sort((a, b) => b.by - a.by)[0];
  if (growing && growing.by >= 0.1) return say("spending.lead_growing", { name: growing.r.name, percent: signedPercent(growing.by) });
  const top = [...rows].sort((a, b) => b.total - a.total)[0];
  return top && top.total > 0 ? say("spending.lead_top", { name: top.name.toLowerCase() }) : null;
}

export function treemapItems(rows: SpendingRow[]): { key: string; label: string; value: number; detail: string; hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 }[] {
  const sorted = [...rows].filter((r) => r.total > 0).sort((a, b) => b.total - a.total);
  const hues = [3, 2, 1, 7, 6, 5, 4] as const;
  const top = sorted.slice(0, 7).map((r, i) => ({ key: r.key, label: r.name, value: r.total, detail: moneyWhole(r.total), hue: hues[i]! }));
  const rest = sorted.slice(7).reduce((sum, r) => sum + r.total, 0);
  return rest > 0 ? [...top, { key: "", label: say("spending.rest"), value: rest, detail: moneyWhole(rest), hue: 8 as const }] : top;
}

export interface Movements {
  from: string;
  to: string;
  category: string;
}

export function SpendingView({
  q,
  state,
  scope,
  basic,
  againstLabel,
  onMovements,
}: {
  q: AnalysisQuery;
  state: State;
  scope: Scope;
  basic: Basic;
  againstLabel: string;
  onMovements: (go: Movements) => void;
}) {
  const t = useT();
  const query = { ...q, scope, kind: basic };
  const key = JSON.stringify(query);
  const data = useLoad(() => api.spending(query), key);
  const [open, setOpen] = useState<SpendingRow | null>(null);
  const wide = useWide();

  return (
    <>
      <Loading state={data}>
        {(s) => {
          const change = delta(s.total, s.previous, againstLabel, false);
          const years = crossesYears(s.series.labels);
          const gaps = s.individual_months;
          const columns: TableColumn<SpendingRow>[] = [
            {
              key: "name",
              label: t("spending.category"),
              cell: (r) => (r.ownership === "shared" ? t("spending.shared_name", { name: r.name }) : r.name),
              csv: (r) => (r.ownership === "shared" ? t("spending.shared_name", { name: r.name }) : r.name),
            },
            { key: "total", label: t("spending.amount"), numeric: true, cell: (r) => money(r.total, false), csv: (r) => r.total },
            { key: "share", label: "%", numeric: true, cell: (r) => percentText(r.share), csv: (r) => r.share },
            {
              key: "previous",
              label: t("spending.before"),
              numeric: true,
              cell: (r) => (r.previous ? signedPercent((r.total - r.previous) / r.previous) : "—"),
              csv: (r) => r.previous,
            },
            {
              key: "usual",
              label: t("spending.monthly"),
              numeric: true,
              cell: (r) => money(r.usual, false),
              csv: (r) => Math.round(r.usual * 100) / 100,
            },
          ];
          const lead = spendingLead(s.rows);
          return (
            <>
              {lead && <Heading>{lead}</Heading>}
              {s.rows.some((r) => r.total > 0) && (
                <Treemap
                  label={t("spending.treemap")}
                  items={treemapItems(s.rows)}
                  onSelect={(key) => {
                    const row = s.rows.find((r) => r.key === key);
                    if (row) setOpen(row);
                  }}
                />
              )}
              <StatRow label={t("spending.title")}>
                <StatTile label={t("spending.title")} value={moneyWhole(s.total)} foot={change.text} tone={change.tone} info={t("spending.info_total")} />
                <StatTile
                  label={t("spending.per_month")}
                  value={s.monthly === null ? "—" : moneyWhole(s.monthly)}
                  foot={
                    s.closed_months === 0
                      ? t("spending.current_month")
                      : s.closed_months === 1
                        ? t("spending.closed_one")
                        : t("spending.closed_other", { count: s.closed_months })
                  }
                  info={t("spending.info_average")}
                />
                <StatTile
                  label={t("spending.basic")}
                  value={moneyWhole(s.groups.basic)}
                  foot={s.total ? t("spending.of_spending", { percent: percentText(s.groups.basic / s.total) }) : undefined}
                  info={t("spending.info_basic")}
                />
                <StatTile
                  label={t("spending.not_basic")}
                  value={moneyWhole(s.groups.not_basic + s.groups.not_living)}
                  foot={s.groups.not_living ? t("spending.work", { amount: moneyWhole(s.groups.not_living) }) : t("spending.leisure_travel")}
                  info={t("spending.info_other")}
                />
              </StatRow>
              {gaps.previous < gaps.of && scope !== "shared" && (
                <Hint tone="warning">
                  {t("spending.gaps_previous", { missing: gaps.of - gaps.previous, months: gaps.of })}
                </Hint>
              )}
              {gaps.now < gaps.of && scope !== "shared" && (
                <Hint tone="warning">
                  {t("spending.gaps_now", { missing: gaps.of - gaps.now, months: gaps.of })}
                </Hint>
              )}

              <Section title={t("spending.by_category")}>
                <CategoryBars rows={s.rows} total={s.total} months={s.closed_months} onOpen={setOpen} />
                <DataTable
                  label={t("spending.table")}
                  columns={wide ? columns : columns.filter((c) => c.key === "name" || c.key === "total")}
                  rows={s.rows}
                  rowKey={(r) => r.key}
                  onRowClick={setOpen}
                  footer={
                    wide
                      ? [t("common.total"), money(s.total, false), "", s.previous ? signedPercent((s.total - s.previous) / s.previous) : "—", ""]
                      : [t("common.total"), money(s.total, false)]
                  }
                />
                <CsvButton name={`${t("spending.csv")}-${q.from}-${q.to}`} columns={columns} rows={s.rows} />
                <Hint>
                  {t("spending.before_hint", {
                    against: againstLabel,
                    from: dayText(s.previous_period.from),
                    to: dayText(s.previous_period.to),
                    months: s.usual_months,
                  })}
                </Hint>
              </Section>

              <Section title={t("spending.evolution")}>
                <SeriesChart
                  label={t("spending.chart")}
                  kind="stacked"
                  labels={s.series.labels.map((l) => axisMonth(l, years))}
                  series={s.series.series}
                  order={s.series.series.map((one) => one.key)}
                  format={(v) => money(v, false)}
                  axisFormat={(v) => moneyWhole(v)}
                />
                {s.series.widened && <Hint>{t("spending.widened")}</Hint>}
              </Section>
            </>
          );
        }}
      </Loading>
      {open && (
        <CategorySheet
          q={q}
          row={open}
          state={state}
          onClose={() => setOpen(null)}
          onMovements={onMovements}
        />
      )}
    </>
  );
}

function CategoryBars({
  rows,
  total,
  months,
  onOpen,
}: {
  rows: SpendingRow[];
  total: number;
  months: number;
  onOpen: (r: SpendingRow) => void;
}) {
  const top = Math.max(1, ...rows.map((r) => r.total));
  return (
    <ul className="money-bars" aria-label={say("spending.bars")}>
      {rows
        .filter((r) => r.total > 0)
        .map((r) => {
          const vsUsual = r.usual && r.average !== null ? (r.average - r.usual) / r.usual : null;
          return (
            <li key={r.key}>
              <button type="button" className="money-bar" onClick={() => onOpen(r)}>
                <span className="money-bar-name">
                  {r.name}
                  {r.ownership === "shared" && <span className="money-bar-tag">{say("spending.shared_tag")}</span>}
                </span>
                <span className="money-bar-value">{money(r.total, false)}</span>
                <span className="money-bar-track" aria-hidden="true">
                  <span
                    className="money-bar-fill"
                    data-shared={r.ownership === "shared" ? "" : undefined}
                    style={{ "--bar": `${(r.total / top) * 100}%` } as React.CSSProperties}
                  />
                </span>
                <span className="money-bar-foot">
                  {percentText(total ? r.total / total : 0)}
                  {vsUsual !== null && Math.abs(vsUsual) >= 0.05 && (
                    <span data-tone={vsUsual > 0 ? "negative" : "positive"}>
                      {" · "}
                      {say(months > 1 ? "spending.over_average_month" : "spending.over_average", { percent: signedPercent(vsUsual) })}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
    </ul>
  );
}

function CategorySheet({
  q,
  row,
  state,
  onClose,
  onMovements,
}: {
  q: AnalysisQuery;
  row: SpendingRow;
  state: State;
  onClose: () => void;
  onMovements: (go: Movements) => void;
}) {
  const t = useT();
  const [detail, setDetail] = useState<CategoryDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    api
      .category({ from: q.from, to: q.to, whole: q.whole, name: row.name, ownership: row.ownership })
      .then(setDetail, () => setFailed(true));
  }, [q.from, q.to, q.whole, row.name, row.ownership]);
  const category = state.categories.find((c) => c.name === row.name && c.ownership === row.ownership && c.nature === "expense");
  const shared = row.ownership === "shared" && !q.whole ? t("spending.your_part") : "";

  return (
    <Sheet
      title={row.ownership === "shared" ? t("spending.shared_name", { name: row.name }) : row.name}
      onClose={onClose}
      action={
        category
          ? { label: t("spending.see_movements"), onClick: () => onMovements({ from: q.from, to: q.to, category: category.id }) }
          : undefined
      }
    >
      <p className="money-sheet-total">
        {money(row.total, false)}
        {shared}
      </p>
      {failed && <Hint tone="warning">{t("spending.detail_failed")}</Hint>}
      {!detail && !failed && <Skeleton rows={4} label={t("spending.reading")} />}
      {detail && (
        <>
          {detail.history > 0 && (
            <Hint>
              {t("spending.history", { amount: money(detail.history, false) })}
            </Hint>
          )}
          {detail.merchants.length > 0 && (
            <>
              <GroupLabel>{t("spending.where")}</GroupLabel>
              <List>
                {detail.merchants.slice(0, 12).map((m) => (
                  <ListRow
                    key={m.name}
                    title={m.name}
                    detail={m.count === 1 ? t("spending.times_one") : t("spending.times_other", { count: m.count })}
                    value={money(m.total, false)}
                  />
                ))}
              </List>
            </>
          )}
          {detail.movements.length > 0 && (
            <>
              <GroupLabel>{t("spending.movements")}</GroupLabel>
              <List>
                {detail.movements.slice(0, 40).map((m) => (
                  <ListRow
                    key={m.id}
                    title={m.merchant}
                    subtitle={`${shortDate(m.on)} · ${m.account}`}
                    value={money(-m.amount)}
                  />
                ))}
              </List>
              {detail.movements.length > 40 && <Hint>{t("spending.more", { count: detail.movements.length - 40 })}</Hint>}
            </>
          )}
        </>
      )}
    </Sheet>
  );
}
