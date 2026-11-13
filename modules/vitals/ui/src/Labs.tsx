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
  type Locale,
  useLocale,
  useT,
} from "@openarga/ui";
import { usePreferences } from "@openarga/app";
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
import { PANELS, analyteName, cellShort, cellText, number, panelName, parseNumber, rangeText } from "./labs";
import { plural } from "./words";
import { dayLabel, today } from "./weight";

type Row = LabTable["rows"][number];

const SHOWN = 4;

function checkupLabel(day: string, locale: Locale): string {
  const date = new Date(`${day}T12:00:00Z`);
  const month = date.toLocaleDateString(locale, { month: "short", timeZone: "UTC" }).replace(".", "").slice(0, 3);
  return `${month} ${String(date.getUTCFullYear()).slice(2)}`;
}

export function LabsScreen({ onBack }: { onBack?: () => void } = {}) {
  const t = useT();
  const locale = useLocale();
  const [labs, setLabs] = useState<LabTable | null>(null);
  const [problem, setProblem] = useState("");
  const [picked, setPicked] = useState<Analyte | null>(null);
  const [adding, setAdding] = useState<"checkup" | Checkup | null>(null);

  const load = useCallback(() => {
    readLabs()
      .then(setLabs)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setProblem(t("labs.read_failed"));
      });
  }, [t]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!labs) return;
    const wanted = new URLSearchParams(window.location.search).get("attach");
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
      <ScreenHeader title={t("labs.title")} back={onBack ? { label: t("tabs.health"), onClick: onBack } : undefined} />
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {labs === null && !problem && <Skeleton label={t("labs.loading")} />}

      {labs && checkups.length === 0 && (
        <EmptyState title={t("labs.none_title")}>{t("labs.none_text")}</EmptyState>
      )}

      {labs && (
        <Button variant="tinted" icon="plus" onClick={() => setAdding("checkup")}>
          {t("labs.new")}
        </Button>
      )}

      {labs && labs.rows.length > 0 && (
        <section ref={table} className="vitals-labs" aria-label={t("labs.values_by_checkup")}>
          <Hint>{t("labs.legend")}</Hint>
          <div className="vitals-labs-panels">
            {PANELS.map((panel) => {
              const rows = labs.rows.filter((row) => row.analyte.panel === panel);
              if (rows.length === 0) return null;
              const label = panelName(t, panel);
              return (
                <div key={panel} className="vitals-group">
                  <GroupLabel>{label}</GroupLabel>
                  <DataTable<Row>
                    label={t("labs.panel_values", { panel: label })}
                    rowKey={(row) => row.analyte.id}
                    rows={rows}
                    onRowClick={(row) => setPicked(row.analyte)}
                    columns={[
                      {
                        key: "name",
                        label: t("labs.analyte"),
                        cell: (row) => (
                          <>
                            <span className="vitals-analyte">{analyteName(t, row.analyte)}</span>
                            {row.analyte.unit && <span className="vitals-analyte-unit">{row.analyte.unit}</span>}
                          </>
                        ),
                        csv: (row) => analyteName(t, row.analyte),
                      },
                      ...shown.map((checkup) => ({
                        key: checkup.id,
                        label: checkupLabel(checkup.day, locale),
                        numeric: true,
                        cell: (row: Row) => {
                          const cell = row.cells[checkup.id];
                          if (!cell) return <span className="vitals-value-missing">—</span>;
                          return (
                            <span
                              className="vitals-value"
                              data-out={cell.out ? "" : undefined}
                              title={cellText(cell, locale)}
                              aria-label={cellText(cell, locale)}
                            >
                              {cellShort(cell, locale)}
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
            <Hint>{t("labs.shown", { shown: SHOWN, count: checkups.length })}</Hint>
          )}
        </section>
      )}

      {labs && checkups.length > 0 && (
        <section className="vitals-group">
          <GroupLabel>{t("labs.checkups")}</GroupLabel>
          <List>
            {checkups.map((one) => (
              <ListRow
                key={one.id}
                title={dayLabel(one.day, locale)}
                subtitle={one.center ?? undefined}
                detail={`${plural(t, "labs.values", one.values)}${one.out ? ` · ${t("labs.out", { count: one.out })}` : ""}`}
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
  const t = useT();
  const locale = useLocale();
  const [found, setFound] = useState<Evolution | null>(null);

  useEffect(() => {
    readEvolution(analyte.id)
      .then(setFound)
      .catch(() => setFound({ analyte, points: [], skipped: 0 }));
  }, [analyte]);

  const last = found?.points.at(-1);
  const name = analyteName(t, analyte);
  const aboutKey = `analyte.${analyte.id}.about`;
  const about = t(aboutKey) === aboutKey ? analyte.about : t(aboutKey);

  return (
    <Sheet title={name} onClose={onClose}>
      <div className="vitals-sheet">
        <Hint>{about}</Hint>
        {found === null && <Skeleton label={t("labs.loading_evolution")} />}
        {found && found.points.length === 0 && <Hint>{t("labs.only_text", { unit: analyte.unit ?? "" })}</Hint>}
        {found && found.points.length > 0 && (
          <TrendChart
            label={t("labs.each_checkup", { name })}
            points={found.points.map((one) => ({ day: one.day, value: one.value }))}
            band={last ? { low: last.ref_low || null, high: last.ref_high } : null}
            bandName={t("labs.reference_range")}
            valueName={name}
            format={(value) => number(value, locale, analyte.unit)}
            formatDay={(day) => dayLabel(day, locale)}
          />
        )}
        {last && (
          <Hint>
            {t("labs.last", { value: number(last.value, locale, analyte.unit), day: dayLabel(last.day, locale) })}
            {rangeText(last.ref_low, last.ref_high, locale) &&
              `, ${t("labs.range", { range: rangeText(last.ref_low, last.ref_high, locale, analyte.unit) })}`}
            .
          </Hint>
        )}
        {found && found.skipped > 0 && (
          <Hint>
            {plural(t, "labs.skipped", found.skipped, { unit: analyte.unit ?? "" })}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}

function NewCheckup({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useT();
  const { timezone } = usePreferences();
  const [day, setDay] = useState(() => today(timezone));
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
        setProblem(error instanceof Error ? error.message : t("common.create_failed"));
        setBusy(false);
      });
  };

  return (
    <Sheet
      title={t("labs.new")}
      onClose={onClose}
      action={{ label: busy ? t("common.saving") : t("common.create"), onClick: save, disabled: busy || !day }}
    >
      <div className="vitals-sheet">
        <DateField label={t("common.day")} value={day} onChange={setDay} />
        <TextField label={t("labs.center")} value={center} onChange={setCenter} placeholder={t("labs.center_placeholder")} />
        <label className="text-field-label" htmlFor="vitals-pdf">
          {t("labs.report_pdf")}
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
  const t = useT();
  const locale = useLocale();
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
        setSaying(t("labs.logged", { name: picked ? analyteName(t, picked) : analyte }));
        setValue("");
        setLow("");
        setHigh("");
        onChanged();
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(error instanceof Error ? error.message : t("weight.log_failed"));
      });
  };

  const upload = (file: File) => {
    uploadDocument(checkup.id, file)
      .then(() => {
        setSaying(t("labs.pdf_saved"));
        onChanged();
      })
      .catch((error: unknown) => setSaying(error instanceof Error ? error.message : t("labs.upload_failed")));
  };

  return (
    <Sheet title={dayLabel(checkup.day, locale)} onClose={onClose}>
      <div className="vitals-sheet">
        {checkup.center && <Hint>{checkup.center}</Hint>}
        {checkup.document ? (
          <Button variant="tinted" onClick={() => window.open(documentUrl(checkup.id), "_blank", "noopener")}>
            {t("labs.open_pdf")}
          </Button>
        ) : (
          <Hint>{t("labs.no_pdf")}</Hint>
        )}
        <label className="text-field-label" htmlFor="vitals-pdf-again">
          {checkup.document ? t("labs.replace_pdf") : t("labs.upload_pdf")}
        </label>
        <input
          id="vitals-pdf-again"
          type="file"
          accept="application/pdf"
          onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])}
        />

        <GroupLabel>{t("labs.add_value")}</GroupLabel>
        <SelectField
          label={t("labs.analyte")}
          value={analyte}
          onChange={setAnalyte}
          options={analytes.map((one) => ({ value: one.id, label: analyteName(t, one) }))}
        />
        <div className="vitals-log-fields">
          <TextField label={t("labs.value")} value={value} onChange={setValue} placeholder={t("labs.value_placeholder")} />
          <TextField label={t("labs.unit")} value={unit} onChange={setUnit} placeholder={picked?.unit ?? ""} />
        </div>
        <div className="vitals-log-fields">
          <TextField label={t("labs.range_min")} value={low} onChange={setLow} inputMode="decimal" />
          <TextField label={t("labs.range_max")} value={high} onChange={setHigh} inputMode="decimal" />
        </div>
        <Button variant="primary" block disabled={!value.trim()} onClick={add}>
          {t("weight.log")}
        </Button>
        {saying && <Hint>{saying}</Hint>}
      </div>
    </Sheet>
  );
}
