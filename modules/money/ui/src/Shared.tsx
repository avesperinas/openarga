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
  type Translate,
  dates,
  useT,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { ScreenHeader } from "./Header";
import { type Shared, type SharedEntry, type SharedMonth, type State, api } from "./api";
import { EntrySheet } from "./EntrySheet";
import { capital, categoryIcon, money, moneyWhole, monthName, percentText, shortDay } from "./format";
import { IncomesSheet } from "./IncomesSheet";
import { axisMonth } from "./analysisState";

export function SharedScreen({ state, onChanged }: { state: State; onChanged: () => void }) {
  const t = useT();
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
    toast({ message: settled ? t("shared.settled_toast", { year }) : t("shared.reopened_toast", { year }) });
    changed();
  };

  const years = [...new Set([new Date().getFullYear(), ...state.years])].sort();
  const first = years[0] ?? year;
  const last = years[years.length - 1] ?? year;

  return (
    <Screen label={t("shared.title")}>
      <ScreenHeader title={t("shared.title")} />

      <div className="money-period-step" data-center="">
        <IconButton icon="chevron-left" label={t("shared.previous_year")} onClick={() => setYear(year - 1)} disabled={year <= first} />
        <span className="money-period-title">{year}</span>
        <IconButton icon="chevron-right" label={t("shared.next_year")} onClick={() => setYear(year + 1)} disabled={year >= last} />
      </div>

      {failed && <Notice tone="negative" title={t("shared.load_failed")} action={{ label: t("common.retry"), onClick: load }} />}
      {!data && !failed && <Skeleton rows={5} label={t("shared.loading")} />}
      {data && data.role === "alone" && data.total === 0 && data.entries.length === 0 && (
        <Notice title={t("shared.space_question")} action={{ label: t("shared.pick_space"), onClick: () => setEditingIncomes(true) }}>
          {t("shared.space_body")}
        </Notice>
      )}
      {data && data.role === "member" && !data.has_keeper && (
        <Notice title={t("shared.no_keeper")}>
          {t("shared.no_keeper_body")}
        </Notice>
      )}
      {data && (
        <>
          <Balance data={data} onEdit={data.role === "member" ? undefined : () => setSettling(true)} />
          {data.role === "member" && data.kept_at && <Hint>{keptLine(t, data)}</Hint>}

          <Card>
            <Figures
              label={t("shared.of_year", { year })}
              items={[
                { label: t("shared.spending"), value: moneyWhole(data.total) },
                { label: t("shared.your_part"), value: moneyWhole(data.months.reduce((sum, m) => sum + m.mine, 0)) },
              ]}
            />
            <SplitBar
              label={t("shared.ratio")}
              parts={[
                { label: data.me, value: percentText(data.ratio_me), share: data.ratio_me, hue: 5 },
                { label: data.other, value: percentText(1 - data.ratio_me), share: 1 - data.ratio_me, hue: 6 },
              ]}
            />
            <Hint>
              {t("shared.ratio_hint", { percent: percentText(data.ratio_me) })}
            </Hint>
          </Card>

          {data.months.length > 1 && (
            <Card title={t("shared.month_by_month", { year })}>
              <SeriesChart
                kind="stacked"
                label={t("shared.chart", { year })}
                labels={data.months.map((m) => axisMonth(`${year}-${String(m.month).padStart(2, "0")}`, false))}
                series={[
                  { key: "account", name: t("shared.the_account"), values: data.months.map((m) => m.paid.account) },
                  { key: "me", name: t("shared.you_paid"), values: data.months.map((m) => m.paid.me) },
                  { key: "other", name: t("shared.other_paid", { other: data.other }), values: data.months.map((m) => m.paid.other) },
                ].filter((one) => one.values.some((v) => v > 0))}
                order={["account", "me", "other"]}
                overlay={{ key: "mine", name: t("shared.yours"), values: data.months.map((m) => m.mine) }}
                format={(v) => moneyWhole(v)}
              />
            </Card>
          )}

          <Collapsible
            title={t("shared.by_month")}
            subtitle={
              data.average.total === null
                ? data.months.length === 1
                  ? t("shared.months_one")
                  : t("shared.months_other", { count: data.months.length })
                : t("shared.months_average", { count: data.months.length, amount: money(data.average.total, false) })
            }
          >
            {data.months.length === 0 ? (
              <Hint>{t("shared.nothing_yet")}</Hint>
            ) : (
              <div className="money-months">
                {[...data.months].reverse().map((m) => (
                  <MonthBlock key={m.month} m={m} data={data} />
                ))}
              </div>
            )}
          </Collapsible>

          {data.by_category.length > 0 && (
            <Section title={t("shared.by_category")}>
              <SegmentedControl<"total" | "average">
                label={t("shared.how")}
                value={average ? "average" : "total"}
                onChange={(v) => setAverage(v === "average")}
                options={[
                  { value: "total", label: t("shared.total_year", { year }) },
                  { value: "average", label: t("shared.monthly") },
                ]}
              />
              <PartBars
                label={average ? t("shared.cat_average") : t("shared.cat_year", { year })}
                parts={data.by_category.map((c) => {
                  const amount = average ? (data.average.months ? (data.average.by_category[c.name] ?? 0) : 0) : c.amount;
                  const top = Math.max(...data.by_category.map((one) => one.amount)) || 1;
                  return {
                    label: `${c.name} · ${percentText(c.amount / (data.total || 1))}`,
                    value: average && !data.average.months ? "—" : moneyWhole(amount),
                    share: c.amount / top,
                  };
                })}
              />
              {average && (
                <Hint>
                  {data.average.months === 0
                    ? t("shared.no_closed")
                    : t("shared.closed", { count: data.average.months })}
                </Hint>
              )}
            </Section>
          )}

          <Section title={t("shared.outside")} count={data.entries.length} action={{ label: t("shared.add"), onClick: () => setAdding(true) }}>
            {data.entries.length === 0 ? (
              <EmptyState icon="people" title={t("shared.none_typed")} action={{ label: t("shared.add_expense"), onClick: () => setAdding(true) }}>
                {t("shared.none_typed_body", { other: data.other })}
              </EmptyState>
            ) : (
              <List>
                {data.entries.map((e) => (
                  <ListRow
                    key={e.id}
                    title={e.description}
                    subtitle={t("shared.entry_line", { category: e.category_name, payer: e.payer === "other" ? data.other : data.me, day: shortDay(e.on) })}
                    value={money(e.amount, false)}
                    icon={categoryIcon(e.category_name, "expense")}
                    hue={6}
                    action={{ icon: "trash", label: t("shared.delete", { name: e.description }), onClick: () => setRemoving(e) }}
                  />
                ))}
              </List>
            )}
          </Section>

          {data.role === "member" ? (

            <Section title={t("shared.shared")} action={{ label: t("shared.your_income"), onClick: () => setEditingIncomes(true) }}>
              <Hint>
                {t("shared.member_hint", { other: data.other })}
              </Hint>
            </Section>
          
          ) : (
          <Section title={t("shared.incomes")} action={{ label: t("shared.edit"), onClick: () => setEditingIncomes(true) }}>
            <List>
              {(["me", "other"] as const).map((p) => (
                <ListRow
                  key={p}
                  title={p === "me" ? data.me : data.other}
                  subtitle={t("shared.by_ranges")}
                  value={t("shared.per_year", { amount: money(data.income_totals[p], false) })}
                />
              ))}
            </List>
            {data.incomes.length > 0 && (
              <List>
                {data.incomes.map((i, n) => (
                  <ListRow
                    key={n}
                    title={i.person === "me" ? data.me : data.other}
                    subtitle={t("shared.range", { from: shortDay(i.from), to: shortDay(i.to) })}
                    value={t("shared.per_year", { amount: money(i.salary, false) })}
                    detail={i.extra ? `+ ${money(i.extra, false)}` : undefined}
                  />
                ))}
              </List>
            )}
            <Hint>
              {t("shared.incomes_hint")}
            </Hint>
          </Section>
          )}

          <CreateButton label={t("shared.expense")} onClick={() => setAdding(true)} />
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
            toast({ message: t("shared.recorded") });
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
          title={data.settled ? t("shared.reopen_q", { year }) : t("shared.settle_q", { year })}
          changes={[{ label: t("shared.status"), from: data.settled ? t("shared.settled") : t("shared.unsettled"), to: data.settled ? t("shared.unsettled") : t("shared.settled") }]}
          detail={
            data.settled
              ? t("shared.reopen_detail")
              : t("shared.settle_detail")
          }
          action={data.settled ? t("shared.reopen") : t("shared.mark_settled")}
          onCancel={() => setSettling(false)}
          onConfirm={async () => {
            await settle(!data.settled);
            setSettling(false);
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title={t("shared.delete_q")}
          subject={`${removing.description} · ${money(removing.amount, false)}`}
          consequence={`${t("shared.delete_consequence", { year })} ${CANNOT_UNDO}`}
          action={t("shared.delete_action")}
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

export function keptLine(t: Translate, data: Pick<Shared, "other" | "kept_at">): string {
  if (!data.kept_at) return t("shared.kept", { other: data.other });
  const at = new Date(data.kept_at);
  const time = dates({ hour: "2-digit", minute: "2-digit" }).format(at);
  const day = dates({ day: "numeric", month: "long" }).format(at);
  const today = new Date().toDateString() === at.toDateString();
  return t("shared.kept_at", { other: data.other, when: today ? t("shared.at_time", { time }) : t("shared.on_day", { day }) });
}

function Balance({ data, onEdit }: { data: Shared; onEdit?: () => void }) {
  const t = useT();
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
        amount={even ? t("shared.even") : moneyWhole(owe)}
        detail={
          even
            ? data.settled
              ? t("shared.year_settled", { year: data.year })
              : t("shared.year_unsettled", { year: data.year })
            : t("shared.owes", {
                payer: payer.name,
                payee: payee.name,
                status: data.settled ? t("shared.year_settled", { year: data.year }) : t("shared.closes", { year: data.year }),
              })
        }
        action={
          onEdit ? (
            <Button variant="tinted" size="small" icon={data.settled ? "repeat" : "done"} onClick={onEdit}>
              {data.settled ? t("shared.reopen_year", { year: data.year }) : t("shared.settle_year", { year: data.year })}
            </Button>
          ) : undefined
        }
      />
    </Card>
  );
}

function MonthBlock({ m, data }: { m: SharedMonth; data: Shared }) {
  const t = useT();
  const title = capital(monthName(m.month));
  return (
    <Collapsible title={title} subtitle={`${t("shared.month_sub", { total: money(m.total, false), mine: money(m.mine, false) })}${m.source === "history" ? t("shared.from_history") : ""}`}>
      <ul className="money-month-cats">
        {m.by_category.map((c) => (
          <li key={c.name}>
            <span>
              {c.name}
              <span className="money-part-kind">{c.split === "fifty_fifty" ? t("shared.half") : t("shared.by_income")}</span>
            </span>
            <span className="money-part-amount">{money(c.amount, false)}</span>
          </li>
        ))}
      </ul>
      <dl className="money-month-facts">
        <dt>{t("shared.account_paid")}</dt>
        <dd>{money(m.paid.account, false)}</dd>
        <dt>{t("shared.paid", { name: data.me })}</dt>
        <dd>{money(m.paid.me, false)}</dd>
        <dt>{t("shared.paid", { name: data.other })}</dt>
        <dd>{money(m.paid.other, false)}</dd>
        <dt>{t("shared.deposited", { name: data.me })}</dt>
        <dd>{money(m.deposits.me, false)}</dd>
        <dt>{t("shared.deposited", { name: data.other })}</dt>
        <dd>{money(m.deposits.other, false)}</dd>
        <dt>{t("shared.month_balance")}</dt>
        <dd data-sign={m.balance_me < 0 ? "out" : "in"}>{money(m.balance_me)}</dd>
      </dl>
    </Collapsible>
  );
}
