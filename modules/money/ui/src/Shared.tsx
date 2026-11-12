import {
  BalanceHero,
  Button,
  CANNOT_UNDO,
  Card,
  ConfirmChange,
  Collapsible,
  ConfirmDelete,
  CreateButton,
  EmptyState,
  Figures,
  Hint,
  IconButton,
  List,
  ListRow,
  Notice,
  PartBars,
  Screen,
  Section,
  SegmentedControl,
  SeriesChart,
  Skeleton,
  SplitBar,
  useToast,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { ScreenHeader } from "./Header";
import { type Shared, type SharedEntry, type SharedMonth, type State, api } from "./api";
import { EntrySheet } from "./EntrySheet";
import { capital, categoryIcon, money, moneyWhole, monthName, percentText, shortDay } from "./format";
import { IncomesSheet } from "./IncomesSheet";

export function SharedScreen({ state, onChanged }: { state: State; onChanged: () => void }) {
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [data, setData] = useState<Shared | null>(null);
  const [failed, setFailed] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editingIncomes, setEditingIncomes] = useState(false);
  const [removing, setRemoving] = useState<SharedEntry | null>(null);
  const [settling, setSettling] = useState(false);
  const [average, setAverage] = useState(false);
  const toast = useToast();

  const load = useCallback(() => {
    setFailed(false);
    api.shared(year).then(setData, () => setFailed(true));
  }, [year]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  const changed = () => {
    load();
    onChanged();
  };

  const settle = async (settled: boolean) => {
    await api.settle(year, settled);
    toast({ message: settled ? `${year} liquidado` : `${year} vuelve a estar abierto` });
    changed();
  };

  const years = [...new Set([new Date().getFullYear(), ...state.years])].sort();
  const first = years[0] ?? year;
  const last = years[years.length - 1] ?? year;

  return (
    <Screen label="Compartido">
      <ScreenHeader title="Compartido" />

      <div className="money-period-step" data-center="">
        <IconButton icon="chevron-left" label="Año anterior" onClick={() => setYear(year - 1)} disabled={year <= first} />
        <span className="money-period-title">{year}</span>
        <IconButton icon="chevron-right" label="Año siguiente" onClick={() => setYear(year + 1)} disabled={year >= last} />
      </div>

      {failed && <Notice tone="negative" title="No se ha podido cargar" action={{ label: "Reintentar", onClick: load }} />}
      {!data && !failed && <Skeleton rows={5} label="Cargando lo común" />}
      {data && data.role === "alone" && data.total === 0 && data.entries.length === 0 && (
        <Notice title="¿Lleváis lo común en un espacio de arga?" action={{ label: "Elegir espacio", onClick: () => setEditingIncomes(true) }}>
          Si la cuenta común la tiene la otra persona en su Money, elige el espacio que compartís y aquí verás lo mismo que ella, desde tu lado.
        </Notice>
      )}
      {data && data.role === "member" && !data.has_keeper && (
        <Notice title="Nadie lleva todavía la cuenta común">
          Lo común sale del Money de quien tiene la cuenta común. Cuando elija este espacio en su Compartido, aquí verás lo mismo que ve, desde tu lado.
        </Notice>
      )}
      {data && (
        <>
          <Balance data={data} onEdit={data.role === "member" ? undefined : () => setSettling(true)} />
          {data.role === "member" && data.kept_at && <Hint>{keptLine(data)}</Hint>}

          <Card>
            <Figures
              label={`Lo común de ${year}`}
              items={[
                { label: "Gasto común", value: moneyWhole(data.total) },
                { label: "Tu parte", value: moneyWhole(data.months.reduce((sum, m) => sum + m.mine, 0)) },
              ]}
            />
            <SplitBar
              label="Cómo se reparte lo proporcional, por ingresos"
              parts={[
                { label: data.me, value: percentText(data.ratio_me), share: data.ratio_me, hue: 5 },
                { label: data.other, value: percentText(1 - data.ratio_me), share: 1 - data.ratio_me, hue: 6 },
              ]}
            />
            <Hint>
              Lo que va a medias cuenta la mitad para cada uno; el resto, según los ingresos declarados del año. El tuyo es el{" "}
              {percentText(data.ratio_me)}.
            </Hint>
          </Card>

          {data.months.length > 1 && (
            <Card title={`${year}, mes a mes`}>
              <SeriesChart
                kind="stacked"
                label={`Lo común de cada mes de ${year}, por quién pagó, con lo que te tocaba`}
                labels={data.months.map((m) => monthName(m.month).slice(0, 3))}
                series={[
                  { key: "account", name: "La cuenta común", values: data.months.map((m) => m.paid.account) },
                  { key: "me", name: `Pagaste tú`, values: data.months.map((m) => m.paid.me) },
                  { key: "other", name: `Pagó ${data.other}`, values: data.months.map((m) => m.paid.other) },
                ].filter((one) => one.values.some((v) => v > 0))}
                order={["account", "me", "other"]}
                overlay={{ key: "mine", name: "Lo tuyo", values: data.months.map((m) => m.mine) }}
                format={(v) => moneyWhole(v)}
              />
            </Card>
          )}

          <Collapsible
            title="Por meses"
            subtitle={
              data.average.total === null
                ? `${data.months.length} ${data.months.length === 1 ? "mes" : "meses"}`
                : `${data.months.length} meses · ${money(data.average.total, false)} de media`
            }
          >
            {data.months.length === 0 ? (
              <Hint>Aún no hay nada este año.</Hint>
            ) : (
              <div className="money-months">
                {[...data.months].reverse().map((m) => (
                  <MonthBlock key={m.month} m={m} data={data} />
                ))}
              </div>
            )}
          </Collapsible>

          {data.by_category.length > 0 && (
            <Section title="Por categoría">
              <SegmentedControl<"total" | "average">
                label="Cómo se cuenta"
                value={average ? "average" : "total"}
                onChange={(v) => setAverage(v === "average")}
                options={[
                  { value: "total", label: `Total ${year}` },
                  { value: "average", label: "Media mensual" },
                ]}
              />
              <PartBars
                label={average ? "Lo común de cada categoría, de media al mes" : `Lo común de cada categoría en ${year}`}
                parts={data.by_category.map((c) => {
                  const amount = average ? (data.average.months ? (data.average.by_category[c.name] ?? 0) : 0) : c.amount;
                  const top = Math.max(...data.by_category.map((one) => one.amount)) || 1;
                  return {
                    label: `${c.name} · ${Math.round((c.amount / (data.total || 1)) * 100)} %`,
                    value: average && !data.average.months ? "—" : moneyWhole(amount),
                    share: c.amount / top,
                  };
                })}
              />
              {average && (
                <Hint>
                  {data.average.months === 0
                    ? "Aún no ha acabado ningún mes del año: la media sale cuando cierre el primero."
                    : `Lo de cada categoría entre los ${data.average.months} meses cerrados del año. El mes en curso no entra.`}
                </Hint>
              )}
            </Section>
          )}

          <Section title="Fuera de cuenta" count={data.entries.length} action={{ label: "+ Añadir", onClick: () => setAdding(true) }}>
            {data.entries.length === 0 ? (
              <EmptyState icon="people" title="Nada apuntado a mano" action={{ label: "Apuntar un gasto", onClick: () => setAdding(true) }}>
                Lo que {data.other} paga de su bolsillo, o lo que tú pagas en efectivo sin una retirada que lo explique.
              </EmptyState>
            ) : (
              <List>
                {data.entries.map((e) => (
                  <ListRow
                    key={e.id}
                    title={e.description}
                    subtitle={`${e.category_name} · pagó ${e.payer === "other" ? data.other : data.me} · ${shortDay(e.on)}`}
                    value={money(e.amount, false)}
                    icon={categoryIcon(e.category_name, "expense")}
                    hue={6}
                    action={{ icon: "trash", label: `Borrar ${e.description}`, onClick: () => setRemoving(e) }}
                  />
                ))}
              </List>
            )}
          </Section>

          {data.role === "member" ? (

            <Section title="Lo común" action={{ label: "Tu ingreso", onClick: () => setEditingIncomes(true) }}>
              <Hint>
                Las categorías y liquidar cada año los lleva {data.other} en su Money. Tu ingreso, de tu Carrera o a mano, y el espacio con el que ves
                lo común se eligen en «Tu ingreso».
              </Hint>
            </Section>
          
          ) : (
          <Section title="Ingresos del año" action={{ label: "Editar", onClick: () => setEditingIncomes(true) }}>
            <List>
              {(["me", "other"] as const).map((p) => (
                <ListRow
                  key={p}
                  title={p === "me" ? data.me : data.other}
                  subtitle={
                    data.income_missing.includes(p)
                      ? "De Carrera, aún sin cifra: cuentan sus tramos"
                      : data.income_sources[p] === "carrera"
                        ? "De Carrera"
                        : "A mano, por tramos"
                  }
                  value={`${money(data.income_totals[p], false)} / año`}
                />
              ))}
            </List>
            {data.incomes.length > 0 && (
              <List>
                {data.incomes.map((i, n) => (
                  <ListRow
                    key={n}
                    title={i.person === "me" ? data.me : data.other}
                    subtitle={`Del ${shortDay(i.from)} al ${shortDay(i.to)}`}
                    value={`${money(i.salary, false)} / año`}
                    detail={i.extra ? `+ ${money(i.extra, false)}` : undefined}
                  />
                ))}
              </List>
            )}
            <Hint>
              Deciden qué parte de lo proporcional es de cada uno. Cada año, cada uno a mano (neto anual por tramos de fechas) o de su Carrera (el neto del
              año entero).
            </Hint>
          </Section>
          )}

          <CreateButton label="Gasto" onClick={() => setAdding(true)} />
        </>
      )}

      {adding && data && (
        <EntrySheet
          state={state}
          year={year}
          names={{ me: data.me, other: data.other }}
          common={data.role === "member" ? data.common_categories : undefined}
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            toast({ message: "Gasto apuntado" });
            changed();
          }}
        />
      )}
      {editingIncomes && data && (
        <IncomesSheet
          data={data}
          onClose={() => setEditingIncomes(false)}
          onSaved={() => {
            setEditingIncomes(false);
            changed();
          }}
        />
      )}
      {settling && data && (
        <ConfirmChange
          title={data.settled ? `¿Volver a abrir ${year}?` : `¿Marcar ${year} como liquidado?`}
          changes={[{ label: "Estado", from: data.settled ? "Liquidado" : "Sin liquidar", to: data.settled ? "Sin liquidar" : "Liquidado" }]}
          detail={
            data.settled
              ? "El saldo del año vuelve a contar como pendiente."
              : "Di que ya os habéis puesto a cero por lo de este año. El saldo sigue viéndose, marcado como liquidado."
          }
          action={data.settled ? "Volver a abrir" : "Marcar como liquidado"}
          onCancel={() => setSettling(false)}
          onConfirm={async () => {
            await settle(!data.settled);
            setSettling(false);
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title="¿Borrar este gasto?"
          subject={`${removing.description} · ${money(removing.amount, false)}`}
          consequence={`Deja de contar en lo común de ${year}. ${CANNOT_UNDO}`}
          action="Borrar gasto"
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await api.removeEntry(removing.id);
            setRemoving(null);
            changed();
          }}
        />
      )}
    </Screen>
  );
}

export function keptLine(data: Pick<Shared, "other" | "kept_at">): string {
  if (!data.kept_at) return `Lo lleva ${data.other} en su Money.`;
  const at = new Date(data.kept_at);
  const time = at.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  const day = at.toLocaleDateString("es-ES", { day: "numeric", month: "long" });
  const today = new Date().toDateString() === at.toDateString();
  return `Lo lleva ${data.other} en su Money · al día ${today ? `a las ${time}` : `el ${day}`}. Lo que apuntes entra en el saldo en medio minuto.`;
}

function Balance({ data, onEdit }: { data: Shared; onEdit?: () => void }) {
  const owe = Math.abs(data.balance_me);
  const even = owe < 0.005;
  const me = { name: data.me, hue: 5 as const };
  const other = { name: data.other, hue: 6 as const };
  const [payer, payee] = data.balance_me < 0 ? [me, other] : [other, me];
  return (
    <Card>
      <BalanceHero
        payer={payer}
        payee={payee}
        even={even}
        amount={even ? "Estáis a cero" : moneyWhole(owe)}
        detail={
          even
            ? data.settled
              ? `${data.year} está liquidado`
              : `${data.year}, sin liquidar`
            : `${payer.name} debe a ${payee.name} · ${data.settled ? `${data.year} está liquidado` : `${data.year}, sin liquidar · se liquida al cerrar el año`}`
        }
        action={
          onEdit ? (
            <Button variant="tinted" size="small" icon={data.settled ? "repeat" : "done"} onClick={onEdit}>
              {data.settled ? `Volver a abrir ${data.year}` : `Liquidar ${data.year}`}
            </Button>
          ) : undefined
        }
      />
    </Card>
  );
}

function MonthBlock({ m, data }: { m: SharedMonth; data: Shared }) {
  const title = capital(monthName(m.month));
  return (
    <Collapsible title={title} subtitle={`${money(m.total, false)} · tu parte ${money(m.mine, false)}${m.source === "history" ? " · de Caudal" : ""}`}>
      <ul className="money-month-cats">
        {m.by_category.map((c) => (
          <li key={c.name}>
            <span>
              {c.name}
              <span className="money-part-kind">{c.split === "fifty_fifty" ? "a medias" : "según ingresos"}</span>
            </span>
            <span className="money-part-amount">{money(c.amount, false)}</span>
          </li>
        ))}
      </ul>
      <dl className="money-month-facts">
        <dt>Pagó la cuenta común</dt>
        <dd>{money(m.paid.account, false)}</dd>
        <dt>Pagó {data.me}</dt>
        <dd>{money(m.paid.me, false)}</dd>
        <dt>Pagó {data.other}</dt>
        <dd>{money(m.paid.other, false)}</dd>
        <dt>Ingresó {data.me} en la común</dt>
        <dd>{money(m.deposits.me, false)}</dd>
        <dt>Ingresó {data.other} en la común</dt>
        <dd>{money(m.deposits.other, false)}</dd>
        <dt>Saldo del mes</dt>
        <dd data-sign={m.balance_me < 0 ? "out" : "in"}>{money(m.balance_me)}</dd>
      </dl>
    </Collapsible>
  );
}
