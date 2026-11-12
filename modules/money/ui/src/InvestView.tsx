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
} from "@openarga/ui";
import { useState } from "react";

import { type AnalysisQuery, type Product, api } from "./api";
import { CsvButton, Loading, RowSheet, dayText, narrowColumns, signedPercent, useLoad } from "./analysisParts";
import { CompositionSection } from "./Composition";
import { axisMonth, crossesYears } from "./analysisState";
import { money, moneyWhole } from "./format";
import { useWide } from "./useWide";

const INFO = {
  value: "Lo que valen tus productos de inversión el último día del periodo (o hoy). Un producto compartido, por tu parte, salvo que elijas «Todo».",
  gain: "Lo que valen menos lo que has aportado (lo puesto menos lo sacado) desde el principio. La rentabilidad simple es esa ganancia sobre lo aportado, sin tener en cuenta cuándo lo pusiste.",
  xirr:
    "La TIR: la rentabilidad anual que tendría que haber dado una cuenta para acabar con lo mismo, poniendo cada aportación el día en que la pusiste. Es la que se compara con un depósito o con la inflación. Antes del corte, las aportaciones del histórico van a mitad de su mes.",
  period:
    "Lo ganado en el periodo: lo que valen al final menos lo que valían al empezar y menos lo aportado entre medias. El porcentaje pesa cada aportación por los días que estuvo dentro (Dietz modificado), y no se pasa a anual.",
};

const ALL = "__all__";

export function InvestView({ q, other }: { q: AnalysisQuery; other: string }) {
  const key = JSON.stringify(q);
  const state = useLoad(() => api.investments(q), key);
  const [picked, setPicked] = useState<string>(ALL);
  const [open, setOpen] = useState<Product | null>(null);
  const wide = useWide();

  return (
    <Loading state={state}>
      {(inv) => {
        const t = inv.total;
        if (inv.rows.length === 0)
          return (
            <Hint>
              {q.group?.length || q.account?.length
                ? "Ningún producto con este filtro."
                : "Aún no hay productos de inversión con aportaciones o valor."}
            </Hint>
          );
        const product = inv.rows.find((r) => r.key === picked);
        const series = product ? product.series : sumSeries(inv.rows);
        const years = crossesYears(series.map((p) => p.label));
        const contribYears = crossesYears(inv.contributions.labels);
        const withOther = inv.rows.filter((r) => r.capital_other);
        const columns: TableColumn<Product>[] = [
          { key: "name", label: "Producto", cell: (r) => (r.carried || r.estimated ? `${r.name} ·` : r.name), csv: (r) => r.name },
          { key: "capital", label: "Aportado", numeric: true, cell: (r) => money(r.capital, false), csv: (r) => r.capital },
          { key: "value", label: "Valor", numeric: true, cell: (r) => money(r.value, false), csv: (r) => r.value },
          { key: "gain", label: "Ganancia", numeric: true, cell: (r) => money(r.gain), csv: (r) => r.gain },
          { key: "simple", label: "Simple", numeric: true, cell: (r) => signedPercent(r.simple), csv: (r) => r.simple },
          { key: "xirr", label: "TIR anual", numeric: true, cell: (r) => signedPercent(r.xirr), csv: (r) => r.xirr },
          {
            key: "period",
            label: "En el periodo",
            numeric: true,
            cell: (r) => `${money(r.period_gain)} · ${signedPercent(r.period_return)}`,
            csv: (r) => r.period_gain,
          },
          {
            key: "in",
            label: "Aportado en el periodo",
            numeric: true,
            cell: (r) => money(r.contributed_in_period, false),
            csv: (r) => r.contributed_in_period,
          },
        ];
        const valueChart = (
          <Section title="Valor frente a lo aportado">
            <SelectField
              label="Producto"
              value={product ? picked : ALL}
              onChange={setPicked}
              options={[{ value: ALL, label: "Todos" }, ...inv.rows.map((r) => ({ value: r.key, label: r.name }))]}
            />
            <GainChart
              label={`Valor y capital aportado de ${product ? product.name : "todos los productos"} a final de cada mes`}
              labels={series.map((p) => axisMonth(p.label, years))}
              value={series.map((p) => p.value)}
              contributed={series.map((p) => p.capital)}
              format={(v) => money(v, false)}
            />
            {inv.widened && <Hint>Los 12 meses hasta el final del periodo.</Hint>}
          </Section>
        );
        const contributions = (
          <>
            {inv.contributions.series.length > 0 && (
              <Section title="Aportaciones por mes">
                <SeriesChart
                  label="Lo aportado a cada producto, mes a mes"
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
            <StatRow label="Inversión">
              <StatTile
                label="Valor"
                value={moneyWhole(t.value)}
                foot={`Aportado ${moneyWhole(t.capital)}`}
                info={INFO.value}
              />
              <StatTile
                label="Ganancia"
                value={moneyWhole(t.gain, true)}
                foot={`${signedPercent(t.simple)} sobre lo aportado`}
                tone={t.gain >= 0 ? "positive" : "negative"}
                info={INFO.gain}
              />
              <StatTile
                label="TIR anual"
                value={signedPercent(t.xirr)}
                foot="Con la fecha de cada aportación"
                tone={t.xirr === null ? "neutral" : t.xirr >= 0 ? "positive" : "negative"}
                info={INFO.xirr}
              />
              <StatTile
                label="En el periodo"
                value={moneyWhole(t.period_gain, true)}
                foot={`${signedPercent(t.period_return)} · aportado ${moneyWhole(t.contributed_in_period)}`}
                tone={t.period_gain >= 0 ? "positive" : "negative"}
                info={INFO.period}
              />
            </StatRow>

            {valueChart}

            <Section title="Rentabilidad de cada producto">
              <DataTable
                label="Rentabilidad de cada producto"
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
                        "Total",
                        money(t.capital, false),
                        money(t.value, false),
                        money(t.gain),
                        signedPercent(t.simple),
                        signedPercent(t.xirr),
                        `${money(t.period_gain)} · ${signedPercent(t.period_return)}`,
                        money(t.contributed_in_period, false),
                      ]
                    : ["Total", money(t.value, false), signedPercent(t.xirr)]
                }
              />
              <CsvButton name={`inversion-${inv.on}`} columns={columns} rows={inv.rows} />
              {inv.rows.some((r) => r.estimated) && (
                <Hint>
                  · Estimados a{" "}
                  {dayText(inv.rows.map((r) => r.estimated ?? "").sort().slice(-1)[0] ?? "")} con el precio de sus fondos desde
                  su última foto; se corrigen al subir otra.
                </Hint>
              )}
              {inv.rows.some((r) => r.carried) && (
                <Hint>· Valen lo de su última valoración más lo aportado después; su ganancia de estos días aún no se sabe.</Hint>
              )}
              {withOther.map((r) => (
                <Hint key={r.key}>
                  {r.name}: además de lo tuyo, {other} ha aportado {moneyWhole(r.capital_other ?? 0)}. El valor que ves es tu parte.
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
