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
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { defaults } from "./analysisState";
import { type Flow, type Kpi, type Spending, type State, type Summary, type Worth, api } from "./api";
import { moneyWhole, percentText } from "./format";
import { ScreenHeader } from "./Header";
import { basicByMonth, change, cushion, groupHue, lastByGroup, lastYear, thisMonthSpan } from "./summaryParts";

const INFO: Record<Kpi["key"] | "month", string> = {
  networth:
    "Lo que vale todo lo tuyo menos los inmuebles: cuentas, fondos, plan de pensiones y cripto. Cada cuenta cuenta por tu parte (la común, la mitad). Debajo, cuánto ha cambiado en 12 meses.",
  liquid:
    "El patrimonio sin lo que no puedes sacar cuando quieras, como el plan de pensiones. Debajo, cuánto ha cambiado en 12 meses.",
  cash: "El dinero a mano: cuentas corrientes y de ahorro, sin el fondo de contingencia. Las cuentas comunes cuentan enteras, no por tu parte.",
  emergency:
    "El saldo de la cuenta que es tu fondo de contingencia, contra su objetivo: tu gasto básico mensual por los meses que digas en Ajustes.",
  expense:
    "Lo que gastas al mes, de media en los últimos 12 meses cerrados: lo tuyo y tu parte de lo común, sin lo que no es gasto de vida (Trabajo). Con menos de 12 meses de datos, la media es de los que hay. Debajo, contra los 12 meses anteriores.",
  basic:
    "Lo mismo que el gasto mensual, pero sin lo que no es básico (Viajes, Ocio): lo que necesitas para vivir. Es la base del objetivo del fondo de contingencia.",
  month:
    "Lo que ha entrado este mes y en qué se ha ido: tu gasto y tu parte de lo común, lo que has invertido y lo que queda. Es el Flujo de Análisis para el mes en curso.",
};

interface Loaded {
  summary: Summary;
  worth: Worth | null;
  spending: Spending | null;
  flow: Flow | null;
}

export function SummaryScreen({ state, onPending }: { state: State; onPending: () => void }) {
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
      <Screen label="Resumen">
        <ScreenHeader title="Resumen" />
        <Notice tone="negative" title="No se ha podido calcular" action={{ label: "Reintentar", onClick: load }} />
      </Screen>
    );
  }
  if (!data) {
    return (
      <Screen label="Resumen">
        <ScreenHeader title="Resumen" />
        <Skeleton rows={6} label="Calculando el resumen" />
      </Screen>
    );
  }
  if (data.summary.kpis.every((k) => k.value === null)) {
    return (
      <Screen label="Resumen">
        <ScreenHeader title="Resumen" />
        <EmptyState icon="wallet" title="Aún no hay datos">
          Cuando Money tenga cuentas y movimientos, aquí verás tu patrimonio, tu gasto y tu colchón.
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
  const t = data.flow?.totals;
  const emergency = kpi("emergency");
  const cash = kpi("cash");

  const main = (
    <>
      {waiting > 0 && (
        <Banner hue={3} glyph={<Icon name="alert" />}>
          <Button variant="plain" onClick={onPending}>
            {waiting === 1 ? "1 movimiento por etiquetar" : `${waiting} movimientos por etiquetar`}
          </Button>
        </Banner>
      )}

      <Card>
        <AreaTrend
          label={head?.label ?? "Patrimonio"}
          value={head?.value === null || head?.value === undefined ? "—" : moneyWhole(head.value)}
          delta={head ? change(head.value, head.previous, true) : undefined}
          points={(series?.points ?? []).map((point) => ({ label: point.label, value: point.total }))}
          description={`${head?.label ?? "Patrimonio"} a final de cada mes, los últimos 12 meses`}
          info={INFO[which]}
          aside={
            <SegmentedControl
              label="Qué patrimonio"
              value={which}
              onChange={setWhich}
              options={[
                { value: "networth", label: "Total" },
                { value: "liquid", label: "Líquido" },
              ]}
            />
          }
        >
          {carried.length > 0 && (
            <Collapsible
              title={carried.length === 1 ? "1 cuenta con su última valoración" : `${carried.length} cuentas con su última valoración`}
              subtitle="Valen lo de ese día, no lo de hoy"
            >
              {carried.map((one) => (
                <Hint key={one}>{one}</Hint>
              ))}
            </Collapsible>
          )}
        </AreaTrend>
      </Card>

      {t && t.income + t.member > 0 && (
        <Card title="Este mes, hasta hoy">
          <SplitBar
            label="Lo que entra este mes"
            parts={[
              { label: "Gastas", value: moneyWhole(t.spent + t.common), share: t.spent + t.common, hue: 4 },
              { label: "Inviertes", value: moneyWhole(t.invested), share: t.invested, hue: 5 },
            ]}
            rest={{ label: t.left >= 0 ? "Queda" : "Tiras de ahorros", value: moneyWhole(t.left), share: Math.max(0, t.left) }}
          />
          <KeyFigures
            label="El mes"
            items={[
              { label: "Entra", value: moneyWhole(t.income + t.member), info: INFO.month },
              ...(t.rate !== null && Math.abs(t.rate) <= 1
                ? [{ label: "Tasa de ahorro", value: percentText(t.rate), tone: t.rate >= 0 ? ("positive" as const) : ("negative" as const) }]
                : []),
            ]}
          />
        </Card>
      )}

      <Card title="Gasto al mes">
        <KeyFigures
          label="Gasto al mes"
          items={[expense, basic]
            .filter((k): k is Kpi => Boolean(k))
            .map((k) => {
              const d = change(k.value, k.previous, false, "frente al año anterior");
              return {
                label: k.label,
                value: k.value === null ? "—" : moneyWhole(k.value),
                foot: d?.text ?? k.detail ?? undefined,
                tone: d?.tone ?? ("neutral" as const),
                info: INFO[k.key],
              };
            })}
        />
        {bars && bars.labels.length > 1 && (
          <SeriesChart
            kind="stacked"
            label="Gasto de cada mes, lo básico y lo demás, con tu media"
            labels={bars.labels}
            series={[
              { key: "basic", name: "Básico", values: bars.basic },
              { key: "rest", name: "El resto", values: bars.rest },
            ]}
            order={["basic", "rest"]}
            overlay={expense?.value ? { key: "average", name: "Tu media", values: bars.labels.map(() => expense.value!) } : undefined}
            format={(value) => moneyWhole(value)}
          />
        )}
      </Card>
    </>
  );

  const aside = (
    <>
      {emergency && (
        <Card title="Colchón">
          <RingFigure
            size="medium"
            share={room?.share ?? null}
            value={room ? room.covered.toLocaleString("es-ES", { maximumFractionDigits: 1 }) : "—"}
            label={room ? `de ${months} meses` : "Sin objetivo"}
            detail={
              emergency.value === null ? undefined : `${moneyWhole(emergency.value)}${emergency.target ? ` de ${moneyWhole(emergency.target)}` : ""}`
            }
            tone={room ? (room.share >= 1 ? "positive" : room.share >= 0.5 ? "info" : "warning") : undefined}
          />
          <KeyFigures
            label="El colchón"
            items={[{ label: emergency.label, value: emergency.value === null ? "—" : moneyWhole(emergency.value), info: INFO.emergency }]}
          />
        </Card>
      )}
      {(groups.length > 0 || cash) && (
        <Card title="Dónde está">
          {groups.length > 0 && (
            <SplitBar
              label="Tu patrimonio por tipo"
              parts={groups.map((one) => ({ label: one.group, value: moneyWhole(one.value), share: one.value, hue: groupHue(one.group) }))}
            />
          )}
          {cash && (
            <KeyFigures label="El dinero a mano" items={[{ label: cash.label, value: cash.value === null ? "—" : moneyWhole(cash.value), info: INFO.cash }]} />
          )}
        </Card>
      )}
    </>
  );

  return (
    <Screen wide label="Resumen">
      <ScreenHeader title="Resumen" />
      <Panes main={main} aside={aside} asideLabel="El colchón y dónde está" />
      {state.cutoff && (
        <Hint>
          Los meses antes del {state.cutoff.split("-").reverse().join("/")} salen del histórico de Caudal; desde entonces, de tus bancos.
        </Hint>
      )}
    </Screen>
  );
}
