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
} from "@openarga/ui";
import { useState } from "react";

import { type AnalysisQuery, type WorthRow, api } from "./api";
import { CsvButton, Loading, RowSheet, dayText, delta, narrowColumns, signedPercent, useLoad } from "./analysisParts";
import { axisMonth, crossesYears } from "./analysisState";
import { money, moneyWhole, percentText } from "./format";
import { useWide } from "./useWide";

type By = "group" | "institution" | "account";

const INFO = {
  total:
    "Lo que valen tus cuentas el último día del periodo (o hoy, si aún no ha acabado). Una cuenta compartida cuenta por tu parte, salvo que elijas «Todo». Debajo, contra el día antes de que empiece el periodo.",
  contributed:
    "El dinero que has puesto: las cuentas de efectivo, enteras, y de cada producto lo que has aportado menos lo que has sacado, no lo que vale.",
  growth:
    "Lo que vale menos lo aportado: lo que te han dado los productos. Si es negativo, valen menos de lo que pusiste.",
};

export function WorthView({ q, home }: { q: AnalysisQuery; home: boolean }) {
  const key = JSON.stringify(q);
  const state = useLoad(() => api.worth(q), key);
  const [by, setBy] = useState<By>("group");
  const [open, setOpen] = useState<WorthRow | null>(null);
  const wide = useWide();

  return (
    <Loading state={state}>
      {(w) => {
        if (w.rows.length === 0 && (q.group?.length || q.account?.length)) return <Hint>Ninguna cuenta con este filtro.</Hint>;
        const growth = w.contributed !== null ? w.total - w.contributed : null;
        const change = delta(w.total, w.previous, `el ${dayText(w.before)}`);
        const years = crossesYears(w.points.map((p) => p.label));
        const carried = w.rows.filter((r) => r.carried);
        const estimated = w.rows.filter((r) => r.estimated);
        const shares = shareBy(w.rows, by);
        const columns: TableColumn<WorthRow>[] = [
          { key: "name", label: "Cuenta", cell: (r) => (r.carried || r.estimated ? `${r.name} ·` : r.name), csv: (r) => r.name },
          { key: "institution", label: "Entidad", cell: (r) => r.institution },
          { key: "group", label: "Tipo", cell: (r) => r.group },
          { key: "value", label: "Valor", numeric: true, cell: (r) => money(r.value, false), csv: (r) => r.value },
          {
            key: "change",
            label: "Variación",
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
                  ? `Tu patrimonio sube ${moneyWhole(monthly)} al mes de media`
                  : `Tu patrimonio baja ${moneyWhole(-monthly)} al mes de media`}
              </Heading>
            )}
            <StatRow label="Patrimonio">
              <StatTile label="Patrimonio" value={moneyWhole(w.total)} foot={change.text} tone={change.tone} info={INFO.total} />
              {w.contributed !== null && (
                <StatTile label="Aportado" value={moneyWhole(w.contributed)} foot="Lo que has puesto" info={INFO.contributed} />
              )}
              {growth !== null && (
                <StatTile
                  label="Rendimiento"
                  value={moneyWhole(growth, true)}
                  foot={w.contributed ? `${signedPercent(growth / w.contributed)} sobre lo aportado` : undefined}
                  tone={growth >= 0 ? "positive" : "negative"}
                  info={INFO.growth}
                />
              )}
            </StatRow>

            <Section title="Evolución">
              <SeriesChart
                label="Patrimonio a final de cada mes, por tipo, con lo aportado"
                kind="area"
                labels={w.points.map((p) => axisMonth(p.label, years))}
                series={w.groups.map((g) => ({ key: g, name: g, values: w.points.map((p) => p.by_group[g] ?? 0) }))}
                order={w.groups}
                overlay={{ key: "contributed", name: "Aportado", values: w.points.map((p) => p.contributed) }}
                format={(v) => money(v, false)}
                axisFormat={(v) => moneyWhole(v)}
              />
              {w.widened && <Hint>Los 12 meses hasta el final del periodo: un mes solo no dibuja una evolución.</Hint>}
            </Section>

            <Section title={`Reparto a ${dayText(w.on)}`}>
              <div className="money-split">
                <div className="money-split-side">
                  <SegmentedControl
                    label="Agrupar por"
                    value={by}
                    onChange={setBy}
                    options={[
                      { value: "group", label: "Tipo" },
                      { value: "institution", label: "Entidad" },
                      { value: "account", label: "Cuenta" },
                    ]}
                  />
                  <ShareChart
                    label="Reparto del patrimonio"
                    items={shares}
                    order={by === "group" ? w.groups : undefined}
                    format={(v) => moneyWhole(v)}
                    center={moneyWhole(w.total)}
                  />
                </div>
                <DataTable
                  label="El valor de cada cuenta"
                  columns={wide ? columns : narrowColumns(columns, ["name", "value"])}
                  rows={w.rows}
                  rowKey={(r) => r.key}
                  onRowClick={wide ? undefined : setOpen}
                  footer={
                    wide
                      ? ["Total", "", "", money(w.total, false), w.previous !== null ? money(w.total - w.previous) : "", ""]
                      : ["Total", money(w.total, false)]
                  }
                />
              </div>
              <CsvButton name={`patrimonio-${w.on}`} columns={columns} rows={w.rows} />
              {carried.length > 0 && (
                <Hint>
                  · Valen lo de su última valoración más lo aportado después:{" "}
                  {carried.map((r) => `${r.name} (${r.since ? dayText(r.since) : "—"})`).join(", ")}.
                </Hint>
              )}
              {estimated.length > 0 && (
                <Hint>
                  · Estimados con el precio de sus fondos desde su última foto:{" "}
                  {estimated.map((r) => `${r.name} (a ${r.estimated ? dayText(r.estimated) : "—"})`).join(", ")}. Se
                  corrigen al subir otra.
                </Hint>
              )}
              {!home && <Hint>Sin la vivienda.</Hint>}
              {open && <RowSheet title={open.name} columns={columns} row={open} onClose={() => setOpen(null)} />}
              {w.contributed !== null && w.total > 0 && (
                <Hint>
                  De cada 100 € que tienes, {Math.round((w.contributed / w.total) * 100)} los has puesto tú
                  {growth !== null && growth > 0 ? ` y ${percentText(growth / w.total)} es rendimiento.` : "."}
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
