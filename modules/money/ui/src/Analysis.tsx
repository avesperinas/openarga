import {
  Button,
  DateField,
  MultiSelectField,
  IconButton,
  type IconName,
  Screen,
  SegmentedControl,
  SelectField,
  Sheet,
  Switch,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { FlowView } from "./FlowView";
import { ScreenHeader } from "./Header";
import { InvestView } from "./InvestView";
import { type Movements, SpendingView } from "./SpendingView";
import { WorthView } from "./WorthView";
import type { AnalysisQuery, State } from "./api";
import { useWide } from "./useWide";
import {
  type AnalysisState,
  PERIODS,
  VIEWS,
  type View,
  atEnd,
  bounds,
  defaults,
  fromSearch,
  periodTitle,
  pickable,
  previousLabel,
  step,
  toSearch,
} from "./analysisState";

const ICONS: Record<View, IconName> = {
  worth: "wallet",
  invest: "chart",
  spending: "basket",
  flow: "flow",
};

const USES: Record<View, { home: boolean; whole: boolean; scope: boolean; cycle: boolean; pick: boolean }> = {
  worth: { home: true, whole: true, scope: false, cycle: false, pick: true },
  invest: { home: true, whole: true, scope: false, cycle: false, pick: true },
  spending: { home: false, whole: true, scope: true, cycle: false, pick: false },
  flow: { home: false, whole: true, scope: false, cycle: true, pick: false },
};

function changed(s: AnalysisState, uses: (typeof USES)[View], picked: { groups: string[]; accounts: string[] }): number {
  const d = defaults();
  return [
    uses.pick && picked.groups.length > 0,
    uses.pick && picked.accounts.length > 0,
    s.kind !== d.kind,
    uses.whole && s.whole !== d.whole,
    uses.home && s.home !== d.home,
    uses.cycle && s.cycle !== d.cycle,
    uses.cycle && s.percent !== d.percent,
    uses.cycle && s.rent !== d.rent,
    uses.scope && s.scope !== d.scope,
    uses.scope && s.basic !== d.basic,
  ].filter(Boolean).length;
}

export function AnalysisScreen({ state, onMovements }: { state: State; onMovements: (go: Movements) => void }) {
  const [s, setS] = useState<AnalysisState>(() => fromSearch(window.location.search));
  const [ranging, setRanging] = useState(false);
  const [filtering, setFiltering] = useState(false);
  const wide = useWide();
  const first = Math.min(...(state.years.length ? state.years : [new Date().getFullYear()]));

  useEffect(() => {
    const next = `${window.location.pathname}${toSearch(s)}`;
    if (next !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, "", next);
  }, [s]);

  const set = (change: Partial<AnalysisState>) => setS((current) => ({ ...current, ...change }));
  const { from, to } = bounds(s, first);
  const uses = USES[s.view];
  const options = pickable(state.accounts, s.view, s.home, s.groups);
  const groups = s.groups.filter((g) => options.groups.includes(g));
  const accounts = s.accounts.filter((a) => options.accounts.some((o) => o.value === a));
  const q: AnalysisQuery = { from, to, home: s.home, whole: s.whole, ...(uses.pick && { group: groups, account: accounts }) };
  const against = previousLabel(s.kind);
  const count = changed(s, uses, { groups, accounts });
  const view = VIEWS.find((v) => v.value === s.view);

  const period = (
    <SelectField
      label="Periodo"
      hideLabel={wide}
      value={s.kind}
      onChange={(kind) => {
        set({ kind });
        if (kind === "range") setRanging(true);
      }}
      options={PERIODS}
    />
  );
  const stepper = (
    <div className="money-period-step">
      <IconButton
        icon="chevron-left"
        label="Periodo anterior"
        onClick={() => set(step(s, -1))}
        disabled={s.kind === "range" || s.kind === "all"}
      />
      <button
        type="button"
        className="money-analysis-title"
        onClick={() => s.kind === "range" && setRanging(true)}
        aria-label={s.kind === "range" ? "Cambiar el rango" : undefined}
      >
        {periodTitle(s, first)}
      </button>
      <IconButton icon="chevron-right" label="Periodo siguiente" onClick={() => set(step(s, 1))} disabled={atEnd(s)} />
    </div>
  );
  const whole = uses.whole && (
    <SegmentedControl
      label="Lo común"
      value={s.whole ? "whole" : "mine"}
      onChange={(v) => set({ whole: v === "whole" })}
      options={[
        { value: "mine", label: "Tu parte" },
        { value: "whole", label: "Todo" },
      ]}
    />
  );
  const home = uses.home && (
    <span className="money-analysis-switch">
      <span aria-hidden="true">Vivienda</span>
      <Switch label="Incluir la vivienda" checked={s.home} onChange={(on) => set({ home: on })} />
    </span>
  );
  const pick = uses.pick && (
    <div className="money-analysis-pick">
      <MultiSelectField<string>
        label="Tipo de producto"
        hideLabel={wide}
        all="Todos los tipos"
        values={groups}
        onChange={(next) => {
          const fit = pickable(state.accounts, s.view, s.home, next).accounts;
          set({ groups: next, accounts: s.accounts.filter((a) => fit.some((o) => o.value === a)) });
        }}
        options={options.groups.map((g) => ({ value: g, label: g }))}
      />
      <MultiSelectField<string>
        label="Cuenta"
        hideLabel={wide}
        all="Todas las cuentas"
        values={accounts}
        onChange={(next) => set({ accounts: next })}
        options={options.accounts}
      />
    </div>
  );
  const local = (
    <>
      {uses.scope && (
        <>
          <SegmentedControl
            label="Qué gasto"
            value={s.scope}
            onChange={(scope) => set({ scope })}
            options={[
              { value: "all", label: "Todo" },
              { value: "individual", label: "Individual" },
              { value: "shared", label: "Común" },
            ]}
          />
          <SegmentedControl
            label="Qué tipo"
            value={s.basic}
            onChange={(basic) => set({ basic })}
            options={[
              { value: "all", label: "Todo" },
              { value: "basic", label: "Básico" },
              { value: "other", label: "No básico" },
            ]}
          />
        </>
      )}
      {uses.cycle && (
        <>
          <SegmentedControl
            label="Cómo se parte el tiempo"
            value={s.cycle ? "cycle" : "month"}
            onChange={(v) => set({ cycle: v === "cycle" })}
            options={[
              { value: "cycle", label: "Ciclo de nómina" },
              { value: "month", label: "Mes natural" },
            ]}
          />
          <SegmentedControl
            label="En qué se cuenta"
            value={s.percent ? "percent" : "money"}
            onChange={(v) => set({ percent: v === "percent" })}
            options={[
              { value: "money", label: "Euros" },
              { value: "percent", label: "% de lo que entra" },
            ]}
          />
          <SegmentedControl
            label="El alquiler a la vivienda"
            value={s.rent ? "invest" : "shared"}
            onChange={(v) => set({ rent: v === "invest" })}
            options={[
              { value: "invest", label: "Alquiler: inversión" },
              { value: "shared", label: "Alquiler: gasto común" },
            ]}
          />
        </>
      )}
    </>
  );

  return (
    <Screen wide label="Análisis">
      <ScreenHeader title={wide || !view ? "Análisis" : view.label} />
      <div className="money-analysis-views">
        <SegmentedControl
          label="Qué analizar"
          value={s.view}
          onChange={(next) => set({ view: next })}
          options={VIEWS.map((v) => ({ value: v.value, label: v.label, icon: ICONS[v.value] }))}
          iconsWhenNarrow
        />
      </div>

      {wide ? (
        <>
          <div className="money-analysis-bar" role="group" aria-label="Filtros">
            <div className="money-analysis-period">
              {period}
              {stepper}
            </div>
            {pick}
            {(uses.home || uses.whole) && (
              <div className="money-analysis-toggles">
                {whole}
                {home}
              </div>
            )}
          </div>
          {(uses.scope || uses.cycle) && <div className="money-analysis-local">{local}</div>}
        </>
      ) : (
        <div className="money-analysis-bar" role="group" aria-label="Periodo">
          {stepper}
          <Button icon="filter" variant={count ? "tinted" : "secondary"} onClick={() => setFiltering(true)}>
            {count ? `Filtros · ${count}` : "Filtros"}
          </Button>
        </div>
      )}

      {s.view === "worth" && <WorthView q={q} home={s.home} />}
      {s.view === "invest" && <InvestView q={q} other={state.other} />}
      {s.view === "spending" && (
        <SpendingView q={q} state={state} scope={s.scope} basic={s.basic} againstLabel={against} onMovements={onMovements} />
      )}
      {s.view === "flow" && <FlowView q={q} cycle={s.cycle} percent={s.percent} rent={s.rent} againstLabel={against} />}

      {filtering && (
        <Sheet title="Filtros" onClose={() => setFiltering(false)} action={{ label: "Ver", onClick: () => setFiltering(false) }}>
          <div className="money-analysis-sheet">
            {period}
            {whole}
            {home}
            {local}
            {pick}
          </div>
        </Sheet>
      )}
      {ranging && (
        <RangeSheet
          from={s.from}
          to={s.to}
          cutoff={state.cutoff}
          onClose={() => setRanging(false)}
          onDone={(range) => {
            set({ kind: "range", ...range });
            setRanging(false);
          }}
        />
      )}
    </Screen>
  );
}

function RangeSheet({
  from,
  to,
  cutoff,
  onClose,
  onDone,
}: {
  from: string;
  to: string;
  cutoff: string | null;
  onClose: () => void;
  onDone: (range: { from: string; to: string }) => void;
}) {
  const [a, setA] = useState(from);
  const [b, setB] = useState(to);
  const valid = Boolean(a && b && a <= b);
  return (
    <Sheet title="Rango" onClose={onClose} action={{ label: "Ver este rango", onClick: () => onDone({ from: a, to: b }), disabled: !valid }}>
      <DateField label="Desde" value={a} onChange={setA} />
      <DateField label="Hasta" value={b} onChange={setB} invalid={Boolean(a && b && a > b)} hint={a > b ? "Tiene que ir después de «Desde»" : undefined} />
      <div className="money-analysis-presets">
        <Button variant="secondary" onClick={() => setA(`${new Date().getFullYear()}-01-01`)}>
          Desde enero
        </Button>
        {cutoff && (
          <Button variant="secondary" onClick={() => setA(cutoff)}>
            Desde el corte
          </Button>
        )}
      </div>
    </Sheet>
  );
}
