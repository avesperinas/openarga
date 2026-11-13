import {
  Button,
  DateField,
  EmptyState,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Screen,
  SegmentedControl,
  Sheet,
  Skeleton,
  StatRow,
  StatTile,
  TextField,
  TrendChart,
  useLocale,
  useT,
} from "@openarga/ui";
import { usePreferences } from "@openarga/app";
import { useCallback, useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Entry, Unauthorised, type WeightSummary, correctWeight, logWeight, readWeight, signIn } from "./api";
import { ScreenHeader } from "./Header";
import {
  type Period,
  bandFoot,
  changeTone,
  dayLabel,
  extremes,
  inPeriod,
  kg,
  parseKg,
  periods,
  signedKg,
  sourceName,
  today,
} from "./weight";

const RECENT = 7;

export function WeightScreen({ onBack }: { onBack?: () => void } = {}) {
  const t = useT();
  const locale = useLocale();
  const [summary, setSummary] = useState<WeightSummary | null>(null);
  const [problem, setProblem] = useState("");
  const [period, setPeriod] = useState<Period>("3m");
  const [editing, setEditing] = useState<Entry | null>(null);
  const [allEntries, setAllEntries] = useState(false);

  const load = useCallback(() => {
    readWeight()
      .then((found) => {
        setSummary(found);
        setProblem("");
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("weight.read_failed"));
      });
  }, [t]);

  useEffect(load, [load]);

  const shown = summary ? inPeriod(summary.days, period) : [];
  const range = extremes(shown);
  const band = summary && (summary.goal.weight_min_kg !== null || summary.goal.weight_max_kg !== null)
    ? { low: summary.goal.weight_min_kg, high: summary.goal.weight_max_kg }
    : null;

  return (
    <Screen>
      <ScreenHeader title={t("panel.weight")} back={onBack ? { label: t("tabs.health"), onClick: onBack } : undefined} />

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {summary === null && !problem && <Skeleton label={t("weight.loading")} />}

      {summary && summary.latest && (
        <StatRow label={t("weight.how")}>
          <StatTile
            label={t("heart.mean_7")}
            value={kg(summary.latest.avg7, locale)}
            foot={bandFoot(summary.latest.avg7, summary.goal, summary.against_goal, t, locale)}
            tone={summary.against_goal === "inside" ? "positive" : summary.against_goal ? "warning" : "neutral"}
          />
          <StatTile
            label={t("weight.in_30")}
            value={summary.change_30 === null ? "—" : signedKg(summary.change_30, locale)}
            foot={summary.change_30 === null ? t("weight.none_month_ago") : t("weight.on_average")}
            tone={changeTone(summary.change_30, summary.against_goal)}
          />
          <StatTile
            label={t("weight.in_90")}
            value={summary.change_90 === null ? "—" : signedKg(summary.change_90, locale)}
            foot={summary.change_90 === null ? t("weight.none_three_months_ago") : t("weight.on_average")}
            tone={changeTone(summary.change_90, summary.against_goal)}
          />
        </StatRow>
      )}

      {summary && <LogWeight onLogged={load} />}

      {summary && summary.days.length === 0 && (
        <EmptyState title={t("weight.none_title")}>{t("weight.none_text")}</EmptyState>
      )}

      {summary && summary.days.length > 0 && (
        <section className="surface vitals-card">
          <SegmentedControl
            label={t("figure.period")}
            options={periods(t).map((one) => ({ value: one.id, label: one.label }))}
            value={period}
            onChange={setPeriod}
          />
          <TrendChart
            label={t("weight.over_time")}
            points={shown.map((one) => ({ day: one.day, value: one.kg, average: one.avg7 }))}
            band={band}
            valueName={t("weight.of_day")}
            averageName={t("heart.mean_7")}
            format={(value) => kg(value, locale)}
            formatDay={(day) => dayLabel(day, locale)}
          />
          {range && (
            <Hint>
              {t("weight.range", {
                min: kg(range.min.kg, locale),
                min_day: dayLabel(range.min.day, locale),
                max: kg(range.max.kg, locale),
                max_day: dayLabel(range.max.day, locale),
              })}
            </Hint>
          )}
        </section>
      )}

      {summary && summary.entries.length > 0 && (
        <section className="vitals-group">
          <GroupLabel>{t("weight.latest")}</GroupLabel>
          <List>
            {summary.entries.slice(0, allEntries ? undefined : RECENT).map((one) => (
              <ListRow
                key={one.id}
                title={kg(one.kg, locale)}
                subtitle={sourceName(t, one.source)}
                detail={one.at ? `${dayLabel(one.day, locale)}, ${one.at.slice(0, 5)}` : dayLabel(one.day, locale)}
                accessory="chevron-right"
                onClick={() => setEditing(one)}
              />
            ))}
          </List>
          {!allEntries && summary.entries.length > RECENT && (
            <Button variant="plain" onClick={() => setAllEntries(true)}>
              {t("weight.see_latest", { count: summary.entries.length })}
            </Button>
          )}
        </section>
      )}

      {editing && (
        <CorrectWeight
          entry={editing}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            load();
          }}
        />
      )}

      <AppVersion />
    </Screen>
  );
}

function LogWeight({ onLogged }: { onLogged: () => void }) {
  const t = useT();
  const locale = useLocale();
  const { timezone } = usePreferences();
  const [text, setText] = useState("");
  const [day, setDay] = useState(() => today(timezone));
  const [saying, setSaying] = useState("");
  const [busy, setBusy] = useState(false);
  const value = parseKg(text);

  const submit = () => {
    if (value === null || busy) return;
    setBusy(true);
    logWeight({ kg: value, day })
      .then(({ already }) => {
        setText("");
        setSaying(already ? t("weight.already") : "");
        onLogged();
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(error instanceof Error ? error.message : t("weight.log_failed"));
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="surface vitals-card vitals-log" aria-label={t("weight.log_title")}>
      <div className="vitals-log-fields">
        <TextField
          label={t("weight.kg_label")}
          value={text}
          onChange={setText}
          inputMode="decimal"
          placeholder={(78.4).toLocaleString(locale)}
          invalid={text.trim() !== "" && value === null}
          hint={text.trim() !== "" && value === null ? t("weight.bounds") : undefined}
          onSubmit={submit}
        />
        <DateField label={t("common.day")} value={day} onChange={setDay} />
      </div>
      <Button variant="primary" block disabled={value === null || busy} onClick={submit}>
        {t("weight.log")}
      </Button>
      {saying && <Hint>{saying}</Hint>}
    </section>
  );
}

function CorrectWeight({ entry, onClose, onDone }: { entry: Entry; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const locale = useLocale();
  const [text, setText] = useState(entry.kg.toLocaleString(locale));
  const [day, setDay] = useState(entry.day);
  const [problem, setProblem] = useState("");
  const value = parseKg(text);

  const save = () => {
    if (value === null) return;
    correctWeight(entry.id, { kg: value, day, at: entry.at, note: entry.note })
      .then(onDone)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Error ? error.message : t("weight.correct_failed"));
      });
  };

  return (
    <Sheet title={t("weight.correct_title")} onClose={onClose} action={{ label: t("common.save"), onClick: save, disabled: value === null }}>
      <div className="vitals-sheet">
        <TextField
          label={t("weight.kg_label")}
          value={text}
          onChange={setText}
          inputMode="decimal"
          invalid={value === null}
          hint={value === null ? t("weight.bounds") : undefined}
          onSubmit={save}
        />
        <DateField label={t("common.day")} value={day} onChange={setDay} />
        <Hint>{sourceName(t, entry.source)}</Hint>
        {problem && (
          <Hint tone="warning">
            {problem}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}
