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
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { type AnalysisQuery, type CategoryDetail, type SpendingRow, type State, api } from "./api";
import { CsvButton, Loading, dayText, delta, shortDate, signedPercent, useLoad } from "./analysisParts";
import { type Basic, type Scope, axisMonth, crossesYears } from "./analysisState";
import { money, moneyWhole, percentText } from "./format";
import { useWide } from "./useWide";

export function spendingLead(rows: SpendingRow[]): string | null {
  const growing = rows
    .filter((r) => r.average !== null && r.usual > 0 && r.total > 0)
    .map((r) => ({ r, by: (r.average as number) / r.usual - 1 }))
    .sort((a, b) => b.by - a.by)[0];
  if (growing && growing.by >= 0.1) return `${growing.r.name} es lo que más se va de su media: ${signedPercent(growing.by)}`;
  const top = [...rows].sort((a, b) => b.total - a.total)[0];
  return top && top.total > 0 ? `En lo que más gastas es en ${top.name.toLowerCase()}` : null;
}

export function treemapItems(rows: SpendingRow[]): { key: string; label: string; value: number; detail: string; hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 }[] {
  const sorted = [...rows].filter((r) => r.total > 0).sort((a, b) => b.total - a.total);
  const hues = [3, 2, 1, 7, 6, 5, 4] as const;
  const top = sorted.slice(0, 7).map((r, i) => ({ key: r.key, label: r.name, value: r.total, detail: moneyWhole(r.total), hue: hues[i]! }));
  const rest = sorted.slice(7).reduce((sum, r) => sum + r.total, 0);
  return rest > 0 ? [...top, { key: "", label: "El resto", value: rest, detail: moneyWhole(rest), hue: 8 as const }] : top;
}

const INFO = {
  total:
    "Lo que has gastado en el periodo: lo tuyo y, de lo común, tu parte (la mitad, o tu ratio de ingresos del año), salvo que elijas «Todo». Una devolución resta de su categoría. Debajo, contra el periodo anterior; si el periodo aún no ha acabado, contra los mismos días del anterior.",
  average: "El gasto de los meses ya cerrados del periodo dividido entre ellos. El mes en curso no entra: lleva solo parte del gasto y bajaría la media.",
  basic: "Lo que no es ocio ni viajes ni trabajo: lo que necesitas para vivir.",
  other: "Lo que no es básico (ocio, viajes) y lo que no es gasto de vida (trabajo).",
};

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
              label: "Categoría",
              cell: (r) => (r.ownership === "shared" ? `${r.name} (común)` : r.name),
              csv: (r) => `${r.name}${r.ownership === "shared" ? " (común)" : ""}`,
            },
            { key: "total", label: "Importe", numeric: true, cell: (r) => money(r.total, false), csv: (r) => r.total },
            { key: "share", label: "%", numeric: true, cell: (r) => percentText(r.share), csv: (r) => r.share },
            {
              key: "previous",
              label: "Antes",
              numeric: true,
              cell: (r) => (r.previous ? signedPercent((r.total - r.previous) / r.previous) : "—"),
              csv: (r) => r.previous,
            },
            {
              key: "usual",
              label: "Media mensual",
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
                  label="Lo gastado en el periodo, en bloques del tamaño de cada categoría"
                  items={treemapItems(s.rows)}
                  onSelect={(key) => {
                    const row = s.rows.find((r) => r.key === key);
                    if (row) setOpen(row);
                  }}
                />
              )}
              <StatRow label="Gasto">
                <StatTile label="Gasto" value={moneyWhole(s.total)} foot={change.text} tone={change.tone} info={INFO.total} />
                <StatTile
                  label="Al mes"
                  value={s.monthly === null ? "—" : moneyWhole(s.monthly)}
                  foot={
                    s.closed_months === 0
                      ? "Mes en curso"
                      : `${s.closed_months} ${s.closed_months === 1 ? "mes cerrado" : "meses cerrados"}`
                  }
                  info={INFO.average}
                />
                <StatTile
                  label="Básico"
                  value={moneyWhole(s.groups.basic)}
                  foot={s.total ? `${percentText(s.groups.basic / s.total)} del gasto` : undefined}
                  info={INFO.basic}
                />
                <StatTile
                  label="No básico"
                  value={moneyWhole(s.groups.not_basic + s.groups.not_living)}
                  foot={s.groups.not_living ? `Trabajo ${moneyWhole(s.groups.not_living)}` : "Ocio y viajes"}
                  info={INFO.other}
                />
              </StatRow>
              {gaps.previous < gaps.of && scope !== "shared" && (
                <Hint tone="warning">
                  En {gaps.of - gaps.previous} de los {gaps.of} meses del periodo anterior no hay gasto individual apuntado: la
                  comparación sale a tu favor.
                </Hint>
              )}
              {gaps.now < gaps.of && scope !== "shared" && (
                <Hint tone="warning">
                  En {gaps.of - gaps.now} de los {gaps.of} meses de este periodo no hay gasto individual apuntado.
                </Hint>
              )}

              <Section title="Por categoría">
                <CategoryBars rows={s.rows} total={s.total} months={s.closed_months} onOpen={setOpen} />
                <DataTable
                  label="Gasto por categoría"
                  columns={wide ? columns : columns.filter((c) => c.key === "name" || c.key === "total")}
                  rows={s.rows}
                  rowKey={(r) => r.key}
                  onRowClick={setOpen}
                  footer={
                    wide
                      ? ["Total", money(s.total, false), "", s.previous ? signedPercent((s.total - s.previous) / s.previous) : "—", ""]
                      : ["Total", money(s.total, false)]
                  }
                />
                <CsvButton name={`gasto-${q.from}-${q.to}`} columns={columns} rows={s.rows} />
                <Hint>
                  «Antes» es {againstLabel} ({dayText(s.previous_period.from)} – {dayText(s.previous_period.to)}). La media
                  mensual, de los últimos {s.usual_months} meses cerrados con gasto.
                </Hint>
              </Section>

              <Section title="Evolución">
                <SeriesChart
                  label="Gasto de cada mes, por categoría"
                  kind="stacked"
                  labels={s.series.labels.map((l) => axisMonth(l, years))}
                  series={s.series.series}
                  order={s.series.series.map((one) => one.key)}
                  format={(v) => money(v, false)}
                  axisFormat={(v) => moneyWhole(v)}
                />
                {s.series.widened && <Hint>Los 12 meses hasta el final del periodo.</Hint>}
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
    <ul className="money-bars" aria-label="Categorías por importe">
      {rows
        .filter((r) => r.total > 0)
        .map((r) => {
          const vsUsual = r.usual && r.average !== null ? (r.average - r.usual) / r.usual : null;
          return (
            <li key={r.key}>
              <button type="button" className="money-bar" onClick={() => onOpen(r)}>
                <span className="money-bar-name">
                  {r.name}
                  {r.ownership === "shared" && <span className="money-bar-tag">común</span>}
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
                      {signedPercent(vsUsual)} {months > 1 ? "al mes " : ""}sobre su media
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
  const [detail, setDetail] = useState<CategoryDetail | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    api
      .category({ from: q.from, to: q.to, whole: q.whole, name: row.name, ownership: row.ownership })
      .then(setDetail, () => setFailed(true));
  }, [q.from, q.to, q.whole, row.name, row.ownership]);
  const category = state.categories.find((c) => c.name === row.name && c.ownership === row.ownership && c.nature === "expense");
  const shared = row.ownership === "shared" && !q.whole ? " (tu parte)" : "";

  return (
    <Sheet
      title={row.ownership === "shared" ? `${row.name} (común)` : row.name}
      onClose={onClose}
      action={
        category
          ? { label: "Ver en Movimientos", onClick: () => onMovements({ from: q.from, to: q.to, category: category.id }) }
          : undefined
      }
    >
      <p className="money-sheet-total">
        {money(row.total, false)}
        {shared}
      </p>
      {failed && <Hint tone="warning">No se ha podido leer el detalle.</Hint>}
      {!detail && !failed && <Skeleton rows={4} label="Leyendo la categoría" />}
      {detail && (
        <>
          {detail.history > 0 && (
            <Hint>
              {money(detail.history, false)} son de meses del histórico de Caudal, que guarda la suma del mes y no sus
              movimientos.
            </Hint>
          )}
          {detail.merchants.length > 0 && (
            <>
              <GroupLabel>Dónde</GroupLabel>
              <List>
                {detail.merchants.slice(0, 12).map((m) => (
                  <ListRow
                    key={m.name}
                    title={m.name}
                    detail={`${m.count} ${m.count === 1 ? "vez" : "veces"}`}
                    value={money(m.total, false)}
                  />
                ))}
              </List>
            </>
          )}
          {detail.movements.length > 0 && (
            <>
              <GroupLabel>Movimientos</GroupLabel>
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
              {detail.movements.length > 40 && <Hint>Y {detail.movements.length - 40} más: el resto, en Movimientos.</Hint>}
            </>
          )}
        </>
      )}
    </Sheet>
  );
}
