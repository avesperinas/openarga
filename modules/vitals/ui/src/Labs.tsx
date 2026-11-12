import {
  Button,
  DataTable,
  DateField,
  EmptyState,
  GroupLabel,
  Hint,
  List,
  ListRow,
  Screen,
  SelectField,
  Sheet,
  Skeleton,
  TextField,
  TrendChart,
} from "@openarga/ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Analyte,
  type Checkup,
  type Evolution,
  type LabTable,
  Unauthorised,
  addResult,
  documentUrl,
  readAnalytes,
  readEvolution,
  readLabs,
  recordCheckup,
  signIn,
  uploadDocument,
} from "./api";
import { ScreenHeader } from "./Header";
import { PANELS, cellShort, cellText, number, parseNumber, rangeText } from "./labs";
import { dayLabel, today } from "./weight";

type Row = LabTable["rows"][number];

const SHOWN = 4;

function checkupLabel(day: string): string {
  const date = new Date(`${day}T12:00:00Z`);
  const month = date.toLocaleDateString("es-ES", { month: "short", timeZone: "UTC" }).replace(".", "").slice(0, 3);
  return `${month} ${String(date.getUTCFullYear()).slice(2)}`;
}

export function LabsScreen({ onBack }: { onBack?: () => void } = {}) {
  const [labs, setLabs] = useState<LabTable | null>(null);
  const [problem, setProblem] = useState("");
  const [picked, setPicked] = useState<Analyte | null>(null);
  const [adding, setAdding] = useState<"checkup" | Checkup | null>(null);

  const load = useCallback(() => {
    readLabs()
      .then(setLabs)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem("No se pudieron leer las analíticas.");
      });
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    if (!labs) return;
    const wanted = new URLSearchParams(window.location.search).get("adjuntar");
    const found = wanted ? labs.checkups.find((one) => one.id === wanted) : undefined;
    if (found) {
      setAdding(found);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [labs]);

  const table = useRef<HTMLElement>(null);
  useEffect(() => {
    table.current?.querySelectorAll<HTMLElement>(".data-table-scroll").forEach((one) => {
      one.scrollLeft = one.scrollWidth;
    });
  }, [labs]);

  const checkups = labs?.checkups ?? [];
  const shown = checkups.slice(0, SHOWN).reverse();

  return (
    <Screen>
      <ScreenHeader title="Analíticas" back={onBack ? { label: "Salud", onClick: onBack } : undefined} />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {labs === null && !problem && <Skeleton label="Cargando las analíticas" />}

      {labs && checkups.length === 0 && (
        <EmptyState title={"Todavía no hay revisiones"}>Dale el PDF de una revisión a Claude y pídele que la cargue en Vitals, o créala aquí y añade sus valores.</EmptyState>
      )}

      {labs && (
        <Button variant="tinted" icon="plus" onClick={() => setAdding("checkup")}>
          Nueva revisión
        </Button>
      )}

      {labs && labs.rows.length > 0 && (
        <section ref={table} className="vitals-labs" aria-label="Valores por revisión">
          <Hint>
            En rojo y con flecha, lo que queda fuera del rango de ese informe. Toca un analito para ver su evolución.
          </Hint>
          <div className="vitals-labs-panels">
            {PANELS.map((panel) => {
              const rows = labs.rows.filter((row) => row.analyte.panel === panel.id);
              if (rows.length === 0) return null;
              return (
                <div key={panel.id} className="vitals-group">
                  <GroupLabel>{panel.label}</GroupLabel>
                  <DataTable<Row>
                    label={`${panel.label}: valores por revisión`}
                    rowKey={(row) => row.analyte.id}
                    rows={rows}
                    onRowClick={(row) => setPicked(row.analyte)}
                    columns={[
                      {
                        key: "name",
                        label: "Analito",
                        cell: (row) => (
                          <>
                            <span className="vitals-analyte">{row.analyte.name}</span>
                            {row.analyte.unit && <span className="vitals-analyte-unit">{row.analyte.unit}</span>}
                          </>
                        ),
                        csv: (row) => row.analyte.name,
                      },
                      ...shown.map((checkup) => ({
                        key: checkup.id,
                        label: checkupLabel(checkup.day),
                        numeric: true,
                        cell: (row: Row) => {
                          const cell = row.cells[checkup.id];
                          if (!cell) return <span className="vitals-value-missing">—</span>;
                          return (
                            <span
                              className="vitals-value"
                              data-out={cell.out ? "" : undefined}
                              title={cellText(cell)}
                              aria-label={cellText(cell)}
                            >
                              {cellShort(cell)}
                            </span>
                          );
                        },
                        csv: (row: Row) => row.cells[checkup.id]?.value ?? row.cells[checkup.id]?.value_text ?? null,
                      })),
                    ]}
                  />
                </div>
              );
            })}
          </div>
          {checkups.length > shown.length && (
            <Hint>
              Se ven las {SHOWN} revisiones más recientes; al tocar un analito, su evolución trae las {checkups.length}.
            </Hint>
          )}
        </section>
      )}

      {labs && checkups.length > 0 && (
        <section className="vitals-group">
          <GroupLabel>Revisiones</GroupLabel>
          <List>
            {checkups.map((one) => (
              <ListRow
                key={one.id}
                title={dayLabel(one.day)}
                subtitle={one.center ?? undefined}
                detail={`${one.values} ${one.values === 1 ? "valor" : "valores"}${one.out ? ` · ${one.out} fuera` : ""}`}
                tone={one.out ? "warning" : undefined}
                accessory="chevron-right"
                onClick={() => setAdding(one)}
              />
            ))}
          </List>
        </section>
      )}

      {picked && <EvolutionSheet analyte={picked} onClose={() => setPicked(null)} />}
      {adding === "checkup" && (
        <NewCheckup
          onClose={() => setAdding(null)}
          onDone={() => {
            setAdding(null);
            load();
          }}
        />
      )}
      {adding && adding !== "checkup" && (
        <CheckupSheet
          checkup={adding}
          onClose={() => setAdding(null)}
          onChanged={load}
        />
      )}
      <AppVersion />
    </Screen>
  );
}

export function EvolutionSheet({ analyte, onClose }: { analyte: Analyte; onClose: () => void }) {
  const [found, setFound] = useState<Evolution | null>(null);

  useEffect(() => {
    readEvolution(analyte.id)
      .then(setFound)
      .catch(() => setFound({ analyte, points: [], skipped: 0 }));
  }, [analyte]);

  const last = found?.points.at(-1);

  return (
    <Sheet title={analyte.name} onClose={onClose}>
      <div className="vitals-sheet">
        <Hint>{analyte.about}</Hint>
        {found === null && <Skeleton label="Cargando la evolución" />}
        {found && found.points.length === 0 && (
          <Hint>Solo hay valores en texto, o en una unidad que no se sabe pasar a {analyte.unit}.</Hint>
        )}
        {found && found.points.length > 0 && (
          <TrendChart
            label={`${analyte.name} en cada revisión`}
            points={found.points.map((one) => ({ day: one.day, value: one.value }))}
            band={last ? { low: last.ref_low || null, high: last.ref_high } : null}
            bandName="Rango de referencia"
            valueName={analyte.name}
            format={(value) => number(value, analyte.unit)}
            formatDay={(day) => dayLabel(day)}
          />
        )}
        {last && (
          <Hint>
            Último: {number(last.value, analyte.unit)} el {dayLabel(last.day)}
            {rangeText(last.ref_low, last.ref_high) && `, rango ${rangeText(last.ref_low, last.ref_high, analyte.unit)}`}.
          </Hint>
        )}
        {found && found.skipped > 0 && (
          <Hint>
            {found.skipped} {found.skipped === 1 ? "valor está" : "valores están"} en una unidad que no se sabe pasar a{" "}
            {analyte.unit}: salen en la tabla.
          </Hint>
        )}
      </div>
    </Sheet>
  );
}

function NewCheckup({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [day, setDay] = useState(today());
  const [center, setCenter] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const save = () => {
    setBusy(true);
    recordCheckup(day, center.trim() || null)
      .then(async (created) => {
        if (file) await uploadDocument(created.id, file);
        onDone();
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(error instanceof Error ? error.message : "No se pudo crear.");
        setBusy(false);
      });
  };

  return (
    <Sheet title="Nueva revisión" onClose={onClose} action={{ label: busy ? "Guardando…" : "Crear", onClick: save, disabled: busy || !day }}>
      <div className="vitals-sheet">
        <DateField label="Día" value={day} onChange={setDay} />
        <TextField label="Centro" value={center} onChange={setCenter} placeholder="El servicio de prevención" />
        <label className="text-field-label" htmlFor="vitals-pdf">
          PDF del informe
        </label>
        <input id="vitals-pdf" type="file" accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
        {problem && (
          <Hint tone="warning">
            {problem}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}

function CheckupSheet({ checkup, onClose, onChanged }: { checkup: Checkup; onClose: () => void; onChanged: () => void }) {
  const [analytes, setAnalytes] = useState<Analyte[]>([]);
  const [analyte, setAnalyte] = useState("ldl");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [saying, setSaying] = useState("");

  useEffect(() => {
    void readAnalytes().then(setAnalytes).catch(() => undefined);
  }, []);

  const picked = analytes.find((one) => one.id === analyte);
  const numeric = parseNumber(value);

  const add = () => {
    addResult(checkup.id, {
      analyte,
      value: numeric,
      value_text: numeric === null ? value.trim() || null : null,
      unit: unit.trim() || picked?.unit || null,
      ref_low: parseNumber(low),
      ref_high: parseNumber(high),
    })
      .then(() => {
        setSaying(`${picked?.name ?? analyte} apuntado.`);
        setValue("");
        setLow("");
        setHigh("");
        onChanged();
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(error instanceof Error ? error.message : "No se pudo apuntar.");
      });
  };

  const upload = (file: File) => {
    uploadDocument(checkup.id, file)
      .then(() => {
        setSaying("PDF guardado.");
        onChanged();
      })
      .catch((error: unknown) => setSaying(error instanceof Error ? error.message : "No se pudo subir."));
  };

  return (
    <Sheet title={dayLabel(checkup.day)} onClose={onClose}>
      <div className="vitals-sheet">
        {checkup.center && <Hint>{checkup.center}</Hint>}
        {checkup.document ? (
          <Button variant="tinted" onClick={() => window.open(documentUrl(checkup.id), "_blank", "noopener")}>
            Abrir el PDF
          </Button>
        ) : (
          <Hint>Sin PDF todavía.</Hint>
        )}
        <label className="text-field-label" htmlFor="vitals-pdf-again">
          {checkup.document ? "Sustituir el PDF" : "Subir el PDF"}
        </label>
        <input
          id="vitals-pdf-again"
          type="file"
          accept="application/pdf"
          onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])}
        />

        <GroupLabel>Añadir o corregir un valor</GroupLabel>
        <SelectField
          label="Analito"
          value={analyte}
          onChange={setAnalyte}
          options={analytes.map((one) => ({ value: one.id, label: one.name }))}
        />
        <div className="vitals-log-fields">
          <TextField label="Valor" value={value} onChange={setValue} placeholder="133 o Negativo" />
          <TextField label="Unidad" value={unit} onChange={setUnit} placeholder={picked?.unit ?? ""} />
        </div>
        <div className="vitals-log-fields">
          <TextField label="Rango, mínimo" value={low} onChange={setLow} inputMode="decimal" />
          <TextField label="Rango, máximo" value={high} onChange={setHigh} inputMode="decimal" />
        </div>
        <Button variant="primary" block disabled={!value.trim()} onClick={add}>
          Apuntar
        </Button>
        {saying && <Hint>{saying}</Hint>}
      </div>
    </Sheet>
  );
}
