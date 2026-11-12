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
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Entry, Unauthorised, type WeightSummary, correctWeight, logWeight, readWeight, signIn } from "./api";
import { ScreenHeader } from "./Header";
import {
  PERIODS,
  type Period,
  SOURCES,
  bandFoot,
  changeTone,
  dayLabel,
  extremes,
  inPeriod,
  kg,
  parseKg,
  signedKg,
  today,
} from "./weight";

const RECENT = 7;

export function WeightScreen({ onBack }: { onBack?: () => void } = {}) {
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
        setProblem("No se pudo leer el peso.");
      });
  }, []);

  useEffect(load, [load]);

  const shown = summary ? inPeriod(summary.days, period) : [];
  const range = extremes(shown);
  const band = summary && (summary.goal.weight_min_kg !== null || summary.goal.weight_max_kg !== null)
    ? { low: summary.goal.weight_min_kg, high: summary.goal.weight_max_kg }
    : null;

  return (
    <Screen>
      <ScreenHeader title="Peso" back={onBack ? { label: "Salud", onClick: onBack } : undefined} />

      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {summary === null && !problem && <Skeleton label="Cargando el peso" />}

      {summary && summary.latest && (
        <StatRow label="Cómo va el peso">
          <StatTile
            label="Media de 7 días"
            value={kg(summary.latest.avg7)}
            foot={bandFoot(summary.latest.avg7, summary.goal, summary.against_goal)}
            tone={summary.against_goal === "inside" ? "positive" : summary.against_goal ? "warning" : "neutral"}
          />
          <StatTile
            label="En 30 días"
            value={summary.change_30 === null ? "—" : signedKg(summary.change_30)}
            foot={summary.change_30 === null ? "Sin pesadas hace un mes" : "de media"}
            tone={changeTone(summary.change_30, summary.against_goal)}
          />
          <StatTile
            label="En 90 días"
            value={summary.change_90 === null ? "—" : signedKg(summary.change_90)}
            foot={summary.change_90 === null ? "Sin pesadas hace tres meses" : "de media"}
            tone={changeTone(summary.change_90, summary.against_goal)}
          />
        </StatRow>
      )}

      {summary && <LogWeight onLogged={load} />}

      {summary && summary.days.length === 0 && (
        <EmptyState title={"Todavía no hay pesadas"}>Apunta la de hoy arriba, o pídeselo a Claude: «apunta 78,4 kilos». Con una semana de pesadas
            sale la media, que es la que dice la tendencia.</EmptyState>
      )}

      {summary && summary.days.length > 0 && (
        <section className="surface vitals-card">
          <SegmentedControl
            label="Periodo"
            options={PERIODS.map((one) => ({ value: one.id, label: one.label }))}
            value={period}
            onChange={setPeriod}
          />
          <TrendChart
            label="El peso en el tiempo"
            points={shown.map((one) => ({ day: one.day, value: one.kg, average: one.avg7 }))}
            band={band}
            valueName="Peso del día"
            averageName="Media de 7 días"
            format={kg}
            formatDay={(day) => dayLabel(day)}
          />
          {range && (
            <Hint>
              Mínimo {kg(range.min.kg)} el {dayLabel(range.min.day)} · máximo {kg(range.max.kg)} el{" "}
              {dayLabel(range.max.day)}
            </Hint>
          )}
        </section>
      )}

      {summary && summary.entries.length > 0 && (
        <section className="vitals-group">
          <GroupLabel>Últimas pesadas</GroupLabel>
          <List>
            {summary.entries.slice(0, allEntries ? undefined : RECENT).map((one) => (
              <ListRow
                key={one.id}
                title={kg(one.kg)}
                subtitle={SOURCES[one.source]}
                detail={one.at ? `${dayLabel(one.day)}, ${one.at.slice(0, 5)}` : dayLabel(one.day)}
                accessory="chevron-right"
                onClick={() => setEditing(one)}
              />
            ))}
          </List>
          {!allEntries && summary.entries.length > RECENT && (
            <Button variant="plain" onClick={() => setAllEntries(true)}>
              Ver las {summary.entries.length} últimas
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
  const [text, setText] = useState("");
  const [day, setDay] = useState(today());
  const [saying, setSaying] = useState("");
  const [busy, setBusy] = useState(false);
  const value = parseKg(text);

  const submit = () => {
    if (value === null || busy) return;
    setBusy(true);
    logWeight({ kg: value, day })
      .then(({ already }) => {
        setText("");
        setSaying(already ? "Esa pesada ya estaba apuntada." : "");
        onLogged();
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(error instanceof Error ? error.message : "No se pudo apuntar.");
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="surface vitals-card vitals-log" aria-label="Apuntar el peso">
      <div className="vitals-log-fields">
        <TextField
          label="Peso (kg)"
          value={text}
          onChange={setText}
          inputMode="decimal"
          placeholder="78,4"
          invalid={text.trim() !== "" && value === null}
          hint={text.trim() !== "" && value === null ? "Entre 20 y 400 kilos" : undefined}
          onSubmit={submit}
        />
        <DateField label="Día" value={day} onChange={setDay} />
      </div>
      <Button variant="primary" block disabled={value === null || busy} onClick={submit}>
        Apuntar
      </Button>
      {saying && <Hint>{saying}</Hint>}
    </section>
  );
}

function CorrectWeight({ entry, onClose, onDone }: { entry: Entry; onClose: () => void; onDone: () => void }) {
  const [text, setText] = useState(entry.kg.toLocaleString("es-ES"));
  const [day, setDay] = useState(entry.day);
  const [problem, setProblem] = useState("");
  const value = parseKg(text);

  const save = () => {
    if (value === null) return;
    correctWeight(entry.id, { kg: value, day, at: entry.at, note: entry.note })
      .then(onDone)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Error ? error.message : "No se pudo corregir.");
      });
  };

  return (
    <Sheet title="Corregir la pesada" onClose={onClose} action={{ label: "Guardar", onClick: save, disabled: value === null }}>
      <div className="vitals-sheet">
        <TextField
          label="Peso (kg)"
          value={text}
          onChange={setText}
          inputMode="decimal"
          invalid={value === null}
          hint={value === null ? "Entre 20 y 400 kilos" : undefined}
          onSubmit={save}
        />
        <DateField label="Día" value={day} onChange={setDay} />
        <Hint>{SOURCES[entry.source]}</Hint>
        {problem && (
          <Hint tone="warning">
            {problem}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}
