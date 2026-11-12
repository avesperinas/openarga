import {
  Button,
  Card,
  ChoiceChips,
  DataTable,
  EmptyState,
  GroupLabel,
  Hint,
  IconButton,
  Figures,
  List,
  ListRow,
  MonthStrip,
  Notice,
  Screen,
  SearchField,
  SegmentedControl,
  Skeleton,
  SplitBar,
  type TableColumn,
} from "@openarga/ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ScreenHeader } from "./Header";
import { api, type Movement, type State } from "./api";
import { FilterSheet } from "./FilterSheet";
import {
  type Filters,
  NO_FILTERS,
  type Period,
  activeCount,
  bounds,
  byDay,
  fromLink,
  matches,
  periodTitle,
  step,
  thisMonth,
  totals,
} from "./filters";
import { dayTitle, money, moneyWhole, monthName, rowIcon, shortDay, subtitle, title } from "./format";
import { MovementSheet } from "./MovementSheet";
import { lastYear } from "./summaryParts";
import { useWide } from "./useWide";

export function categoryTotals(rows: Movement[]): { id: string; name: string; total: number }[] {
  const out = new Map<string, { id: string; name: string; total: number }>();
  for (const m of rows) {
    for (const p of m.parts) {
      if (p.nature !== "expense") continue;
      const one = out.get(p.category) ?? { id: p.category, name: p.category_name, total: 0 };
      one.total -= p.amount;
      out.set(p.category, one);
    }
  }
  return [...out.values()].filter((one) => one.total > 0).sort((a, b) => b.total - a.total);
}

function useMonthly(): { key: string; year: number; month: number; total: number }[] {
  const [months, setMonths] = useState<{ key: string; year: number; month: number; total: number }[]>([]);
  useEffect(() => {
    const span = lastYear();
    api.spending({ ...span, scope: "all", kind: "all" }).then(
      (s) => {
        const [y, m] = span.from.split("-").map(Number);
        setMonths(
          s.series.labels.map((_, index) => {
            const d = new Date(y ?? 2000, (m ?? 1) - 1 + index, 1);
            const total = s.series.series.reduce((sum, one) => sum + (one.values[index] ?? 0), 0);
            return { key: `${d.getFullYear()}-${d.getMonth() + 1}`, year: d.getFullYear(), month: d.getMonth() + 1, total };
          }),
        );
      },
      () => setMonths([]),
    );
  }, []);
  return months;
}

export function MovementsScreen({ state, onChanged }: { state: State; onChanged: () => void }) {
  const [link] = useState(() => fromLink(window.location.search));
  const [period, setPeriod] = useState<Period>(() => link?.period ?? thisMonth());
  const [rows, setRows] = useState<Movement[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [filters, setFilters] = useState<Filters>(() => link?.filters ?? NO_FILTERS);
  const [filtering, setFiltering] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const wide = useWide();
  const monthly = useMonthly();

  const load = useCallback(() => {
    const { from, to } = bounds(period);
    setFailed(false);
    api.movements(from, to).then(setRows, () => setFailed(true));
  }, [period]);

  useEffect(() => {
    setRows(null);
    load();
  }, [load]);

  const [hideTransfers, setHideTransfers] = useState(false);
  const visible = useMemo(
    () => {
      const typeOf = (key: string) => state.accounts.find((a) => a.key === key)?.type;
      return (rows ?? []).filter((m) => matches(m, filters, typeOf) && !(hideTransfers && m.kind === "transfer"));
    },
    [rows, filters, hideTransfers, state.accounts],
  );
  const sum = useMemo(() => totals(visible, filters), [visible, filters]);
  const spentBy = useMemo(() => categoryTotals(rows ?? []), [rows]);
  const waiting = (state.counts.ask ?? 0) + (state.counts.pending ?? 0);
  const review = state.counts.default ?? 0;

  const showStatus = (statuses: Filters["statuses"]) => {
    setFilters({ ...NO_FILTERS, statuses });
    setPeriod({ kind: "year", year: new Date().getFullYear() });
  };

  const replace = (changed: Movement) => {
    setRows((current) => current?.map((m) => (m.id === changed.id ? changed : m)) ?? null);
    onChanged();
  };

  return (
    <Screen wide label="Movimientos">
      <ScreenHeader title="Movimientos" />

      <div className="money-period">
        <SegmentedControl
          label="Periodo"
          value={period.kind === "year" ? "year" : "month"}
          onChange={(kind) =>
            setPeriod(
              kind === "year"
                ? { kind: "year", year: currentYear(period) }
                : { kind: "month", year: currentYear(period), month: currentYear(period) === new Date().getFullYear() ? new Date().getMonth() + 1 : 12 },
            )
          }
          options={[
            { value: "month", label: "Mes" },
            { value: "year", label: "Año" },
          ]}
        />
        <div className="money-period-step">
          <IconButton icon="chevron-left" label="Anterior" onClick={() => setPeriod(step(period, -1))} />
          <span className="money-period-title">{periodTitle(period)}</span>
          <IconButton icon="chevron-right" label="Siguiente" onClick={() => setPeriod(step(period, 1))} />
        </div>
      </div>

      {period.kind === "month" && monthly.length > 0 && (
        <MonthStrip
          label="Elegir mes"
          selected={`${period.year}-${period.month}`}
          onSelect={(key) => {
            const [year, month] = key.split("-").map(Number);
            setPeriod({ kind: "month", year: year ?? period.year, month: month ?? period.month });
          }}
          items={monthly.map((one) => ({
            key: one.key,
            label: monthName(one.month).slice(0, 3),
            value: one.total,
            description: `${monthName(one.month)} de ${one.year}: ${moneyWhole(one.total)} de gasto`,
          }))}
        />
      )}

      {waiting > 0 && (
        <Notice
          tone="warning"
          title={`${waiting} por etiquetar`}
          action={{ label: "Ver", onClick: () => showStatus(["ask", "pending"]) }}
        >
          Efectivo y lo que ninguna regla explica. Hasta que lo etiquetes no cuenta como gasto.
        </Notice>
      )}

      <div className="money-search">
        <SearchField value={filters.text} onChange={(text) => setFilters({ ...filters, text })} placeholder="Buscar comercio, concepto o categoría" label="Buscar en movimientos" />
        <Button icon="filter" variant={activeCount(filters) ? "tinted" : "secondary"} onClick={() => setFiltering(true)}>
          {activeCount(filters) ? `Filtros · ${activeCount(filters)}` : "Filtros"}
        </Button>
      </div>

      {activeCount(filters) > 0 && (
        <div className="money-chips">
          {chips(filters, state).map((chip) => (
            <button key={chip.key} type="button" className="money-chip" onClick={() => setFilters(chip.remove())}>
              {chip.label}
              <span aria-hidden="true">×</span>
              <span className="money-sr">Quitar filtro</span>
            </button>
          ))}
          <button type="button" className="money-chip" data-plain="" onClick={() => setFilters({ ...NO_FILTERS, text: filters.text })}>
            Quitar todos
          </button>
        </div>
      )}

      {rows !== null && (
        <Card>
          <Figures
            label="Lo que suman los movimientos que ves"
            items={[
              { label: "Entra", value: moneyWhole(sum.income), lit: sum.income > 0 },
              { label: "Sale", value: moneyWhole(sum.expense) },
            ]}
          />
          {sum.income > 0 && sum.expense > 0 && sum.income >= sum.expense && (
            <SplitBar
              label="Lo que entra: lo que sale y lo que queda"
              parts={[{ label: "Sale", value: moneyWhole(sum.expense), share: sum.expense, hue: 4 }]}
              rest={{ label: "Queda", value: moneyWhole(sum.income - sum.expense), share: sum.income - sum.expense }}
            />
          )}
          <Hint>
            {sum.count === rows.length ? `${sum.count} movimientos` : `${sum.count} de ${rows.length} movimientos`}
            {sum.expense > sum.income && sum.income > 0 ? ` · sale ${moneyWhole(sum.expense - sum.income)} más de lo que entra` : ""}
          </Hint>
        </Card>
      )}
      {spentBy.length > 1 && (
        <ChoiceChips
          label="Por categoría"
          scroll
          value={filters.categories.length === 1 ? filters.categories[0]! : filters.categories.length === 0 ? "all" : null}
          onChange={(id) => setFilters({ ...filters, categories: id === "all" ? [] : [id] })}
          options={[
            { value: "all", label: "Todo" },
            ...spentBy.slice(0, 8).map((one) => ({ value: one.id, label: `${one.name} ${moneyWhole(one.total)}` })),
          ]}
        />
      )}
      <div className="money-chips">
        <button
          type="button"
          className="money-chip"
          aria-pressed={hideTransfers}
          onClick={() => setHideTransfers(!hideTransfers)}
        >
          {hideTransfers ? "Traspasos ocultos" : "Ocultar traspasos"}
        </button>
        {review > 0 && !filters.statuses.includes("default") && (
          <button type="button" className="money-chip" data-review="" onClick={() => showStatus(["default"])}>
            {review} con la categoría por defecto · Revisar
          </button>
        )}
      </div>

      {failed && <Notice tone="negative" title="No se han podido cargar" action={{ label: "Reintentar", onClick: load }} />}
      {rows === null && !failed && <Skeleton rows={8} label="Cargando movimientos" />}
      {rows !== null && visible.length === 0 && (
        <EmptyState
          icon="list"
          title={rows.length === 0 ? "Sin movimientos" : "Nada con estos filtros"}
          action={rows.length ? { label: "Quitar filtros", onClick: () => setFilters(NO_FILTERS) } : undefined}
        >
          {rows.length === 0 ? `No hay nada en ${periodTitle(period).toLowerCase()}.` : "Prueba con menos filtros o con otro periodo."}
        </EmptyState>
      )}
      {rows !== null && visible.length > 0 &&
        (wide ? <MovementTable rows={visible} onOpen={setOpen} /> : <MovementList rows={visible} onOpen={setOpen} />)}

      {filtering && (
        <FilterSheet state={state} filters={filters} onChange={setFilters} onClose={() => setFiltering(false)} />
      )}
      {open && <MovementSheet id={open} state={state} onClose={() => setOpen(null)} onChanged={replace} onOpen={setOpen} reload={load} />}
    </Screen>
  );
}

function currentYear(p: Period): number {
  return p.kind === "range" ? new Date().getFullYear() : p.year;
}

function MovementList({ rows, onOpen }: { rows: Movement[]; onOpen: (id: string) => void }) {
  return (
    <div className="money-days">
      {byDay(rows).map((day) => (
        <section key={day.on} className="money-day" aria-label={dayTitle(day.on)}>
          <div className="money-day-head">
            <GroupLabel>{dayTitle(day.on)}</GroupLabel>
            {day.net !== 0 && <span className="money-day-net">{money(day.net)}</span>}
          </div>
          <List>
            {day.rows.map((m) => (
              <MovementRow key={m.id} m={m} onOpen={onOpen} />
            ))}
          </List>
        </section>
      ))}
    </div>
  );
}

function MovementRow({ m, onOpen }: { m: Movement; onOpen: (id: string) => void }) {
  const { icon, hue } = rowIcon(m);
  return (
    <ListRow
      title={title(m)}
      subtitle={`${subtitle(m)} · ${m.account_name}`}
      value={money(m.amount)}
      icon={icon}
      hue={hue}
      tone={m.status === "ask" || m.status === "pending" ? "warning" : m.amount > 0 && m.kind !== "transfer" ? "positive" : undefined}
      onClick={() => onOpen(m.id)}
    />
  );
}

function MovementTable({ rows, onOpen }: { rows: Movement[]; onOpen: (id: string) => void }) {
  const columns: TableColumn<Movement>[] = [
    { key: "on", label: "Fecha", cell: (m) => shortDay(m.on), csv: (m) => m.on },
    {
      key: "merchant",
      label: "Concepto",
      cell: (m) => (
        <span className="money-cell-merchant">
          <span className="money-cell-title">{title(m)}</span>
          {m.status === "default" && <span className="money-tag">por defecto</span>}
        </span>
      ),
      csv: (m) => m.merchant,
    },
    { key: "account", label: "Cuenta", cell: (m) => m.account_name, csv: (m) => m.account_name },
    {
      key: "category",
      label: "Qué es",
      cell: (m) => (
        <span className="money-cell-what" data-status={m.status}>
          {subtitle(m)}
        </span>
      ),
      csv: (m) => subtitle(m),
    },
    {
      key: "amount",
      label: "Importe",
      numeric: true,
      cell: (m) => (
        <span className="money-amount" data-sign={m.kind === "transfer" ? "transfer" : m.amount < 0 ? "out" : "in"}>
          {money(m.amount)}
        </span>
      ),
      csv: (m) => m.amount,
    },
  ];
  return (
    <div className="surface money-table">
      <DataTable
        label="Movimientos"
        columns={columns}
        rows={rows}
        rowKey={(m) => m.id}
        onRowClick={(m) => onOpen(m.id)}
        rowTone={(m) => (m.status === "ask" || m.status === "pending" ? "warning" : undefined)}
      />
    </div>
  );
}

interface Chip {
  key: string;
  label: string;
  remove: () => Filters;
}

const WHAT_LABEL = { income: "Ingresos", expense: "Gastos", transfer: "Traspasos", other: "Otros" } as const;
const STATUS_LABEL = {
  ask: "Por etiquetar",
  pending: "Sin interpretar",
  default: "Por defecto",
  manual: "A mano",
  auto: "Automático",
  transfer: "Traspaso",
  return: "Rentabilidad",
  settlement: "Liquidación",
} as const;

function chips(f: Filters, state: State): Chip[] {
  const out: Chip[] = [];
  const without = <K extends keyof Filters>(key: K, value: unknown): Filters => ({
    ...f,
    [key]: (f[key] as unknown[]).filter((v) => v !== value),
  });
  for (const id of f.categories) {
    const c = state.categories.find((c) => c.id === id);
    out.push({ key: `c${id}`, label: c?.name ?? "Categoría", remove: () => without("categories", id) });
  }
  for (const key of f.accounts) {
    out.push({ key: `a${key}`, label: state.accounts.find((a) => a.key === key)?.name ?? key, remove: () => without("accounts", key) });
  }
  for (const name of f.institutions) out.push({ key: `i${name}`, label: name, remove: () => without("institutions", name) });
  for (const type of f.accountTypes) {
    const label = state.accounts.find((a) => a.type === type)?.type_label ?? type;
    out.push({ key: `t${type}`, label, remove: () => without("accountTypes", type) });
  }
  for (const w of f.what) out.push({ key: `w${w}`, label: WHAT_LABEL[w], remove: () => without("what", w) });
  for (const o of f.ownership) {
    out.push({ key: `o${o}`, label: o === "shared" ? "Compartido" : "Individual", remove: () => without("ownership", o) });
  }
  for (const s of f.statuses) out.push({ key: `s${s}`, label: STATUS_LABEL[s], remove: () => without("statuses", s) });
  if (f.min !== null) out.push({ key: "min", label: `Desde ${money(f.min, false)}`, remove: () => ({ ...f, min: null }) });
  if (f.max !== null) out.push({ key: "max", label: `Hasta ${money(f.max, false)}`, remove: () => ({ ...f, max: null }) });
  return out;
}
