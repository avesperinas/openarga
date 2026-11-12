import { Hint, RingFigure, Sankey, Section, StatRow, StatTile } from "@openarga/ui";

import { type AnalysisQuery, api } from "./api";
import { Loading, contract, delta, shortDate, signedPercent, useLoad } from "./analysisParts";
import { money, moneyWhole, percentText } from "./format";
import { useWide } from "./useWide";

const INFO = {
  income:
    "Lo que te entra en el periodo: la nómina y el resto de ingresos. Con «Todo», también lo que pone la otra persona en lo común, para que lo común salga entero.",
  spent: "Tu gasto individual y, de lo común, tu parte (o todo, si lo eliges).",
  invested: (rent: boolean) =>
    rent
      ? "Lo aportado a tus productos de inversión menos lo sacado. Lo pagado a la vivienda como alquiler a medias cuenta aquí, no como gasto."
      : "Lo aportado a tus productos de inversión menos lo sacado. Lo pagado a la vivienda como alquiler cuenta como gasto común, no aquí.",
  left: "Lo que entra menos lo que gastas e inviertes: lo que se queda en tus cuentas. Si es negativo, ese periodo tiraste de ahorros. La tasa de ahorro es lo invertido más lo que queda, sobre lo que entra.",
};

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
  const query = { ...q, cycle, rent };
  const wide = useWide();
  const state = useLoad(() => api.flow(query), JSON.stringify(query));

  return (
    <>
      <Loading state={state}>
        {(f) => {
          const t = f.totals;
          const p = f.previous;
          const spent = t.spent + t.common;
          const open = f.segments.some((s) => s.open);
          const rate = t.rate !== null && Math.abs(t.rate) <= 1 ? t.rate : null;
          const cycles = f.segments.filter((s) => s.kind === "cycle");
          const first = f.segments[0];
          const last = f.segments[f.segments.length - 1];
          if (!first || !last || f.links.length === 0) {
            return <Hint>Nada que enseñar en este periodo.</Hint>;
          }
          const base = t.income + t.member;
          const before = p ? p.income + p.member : 0;
          const share = percent && base > 0;
          const shown = (now: number, sign = false) => (share ? (sign ? signedPercent(now / base) : percentText(now / base)) : moneyWhole(now, sign));
          const card = (now: number, then: number | null, goodUp: boolean) =>
            share ? points(now / base, then !== null && before > 0 ? then / before : null, againstLabel, goodUp) : tile(now, then, againstLabel, goodUp);
          return (
            <>
              <p className="money-analysis-span">
                Del {shortDate(first.from)} al {shortDate(last.to)}
                {open ? " (en curso)" : ""}
                {cycles.length > 0 ? ` · ${cycles.length} ${cycles.length === 1 ? "ciclo" : "ciclos"} de nómina` : ""}
              </p>
              <StatRow label="Flujo">
                <StatTile
                  label="Entra"
                  value={moneyWhole(t.income + t.member)}
                  {...(share ? { foot: "El 100 %" } : tile(t.income + t.member, p ? p.income + p.member : null, againstLabel, true))}
                  info={INFO.income}
                />
                <StatTile
                  label="Gastas"
                  value={shown(spent)}
                  {...card(spent, p ? p.spent + p.common : null, false)}
                  info={INFO.spent}
                />
                <StatTile
                  label="Inviertes"
                  value={shown(t.invested)}
                  {...card(t.invested, p ? p.invested : null, true)}
                  info={INFO.invested(rent)}
                />
                <StatTile
                  label={t.left >= 0 ? "Queda" : "Tiras de ahorros"}
                  value={shown(t.left, true)}
                  foot={rate !== null ? `Tasa de ahorro ${percentText(rate)}` : undefined}
                  tone={t.left >= 0 ? "positive" : "negative"}
                  info={INFO.left}
                />
              </StatRow>
              <Section title="De dónde viene y a dónde va">
                {rate !== null && (
                  <RingFigure
                    size="medium"
                    share={Math.max(0, rate)}
                    value={percentText(rate)}
                    label={rate >= 0 ? `De cada 100 € ahorras ${Math.round(rate * 100)}` : "Tiras de ahorros"}
                    detail="Lo invertido más lo que queda, sobre lo que entra"
                    tone={rate >= 0.2 ? "positive" : rate >= 0 ? "info" : "negative"}
                  />
                )}
                <div className="money-flow">
                  <Sankey
                    label="El dinero del periodo, de los ingresos a cada destino"
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
                  {f.unlogged === 1 ? "Un mes" : `${f.unlogged} meses`} de Caudal no {f.unlogged === 1 ? "tiene" : "tienen"} gasto
                  individual apuntado: lo que quedó en {f.unlogged === 1 ? "él" : "ellos"}, descontado lo que faltó, cuenta como gasto
                  individual «Sin etiquetar». No tiran de tus ahorros: si falta más de lo que queda, la diferencia entra como «Sin
                  etiquetar».
                </Hint>
              )}
              {open && <Hint>El último tramo aún no ha acabado: le falta lo que llegue hasta la próxima nómina.</Hint>}
              {cycle && f.payroll && cycles.length > 0 && (
                <Hint>
                  Cada ciclo va del día en que entra la nómina ({f.payroll}) al anterior a la siguiente, y es del mes que paga: la
                  que entra desde el día 25, del mes siguiente.
                </Hint>
              )}
              {cycle && f.segments.some((s) => s.kind === "month") && (
                <Hint>
                  Antes del corte con Caudal solo hay sumas por mes, así que esos tramos son meses naturales, con la nómina de fin
                  de mes en el siguiente. El primer tramo tras el corte lleva la nómina del último mes de Caudal
                  {f.payroll_moved && f.payroll_moved.in > 0 ? ` (${moneyWhole(f.payroll_moved.in)} aquí)` : ""}.
                </Hint>
              )}
              {p && rate !== null && p.rate !== null && Math.abs(p.rate) <= 1 && (
                <Hint>
                  Tasa de ahorro {percentText(rate)} frente a {percentText(p.rate)} en {againstLabel} (
                  {signedPercent(rate - p.rate).replace(" %", " puntos")}).
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
  if (before === null) return { foot: contract(`Sin dato de ${against}`), tone: "neutral" as const };
  const diff = now - before;
  if (Math.abs(diff) < 0.0005) return { foot: `Igual que ${against}`, tone: "neutral" as const };
  return {
    foot: contract(`${signedPercent(diff).replace(" %", " puntos")} frente a ${against}`),
    tone: (goodUp ? diff > 0 : diff < 0) ? ("positive" as const) : ("negative" as const),
  };
}
