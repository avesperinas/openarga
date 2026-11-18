import { Button, FileField, FilePreview, Hint, Sheet, SelectField, useT } from "@openarga/ui";
import { useState } from "react";

import { type ProductDetail, Refused, type StatementResult, api } from "./api";
import { capital } from "./format";
import { MAX_CHARS, type StatementFormat, formatOf, previewOf } from "./statementFile";

interface Loaded {
  name: string;
  size: number;
  text: string;
  format: StatementFormat;
}

const NONE = "";
const MAPPED = ["booked_on", "description", "amount"] as const;

export function StatementSheet({
  product,
  onBack,
  onImported,
}: {
  product: ProductDetail;
  onBack: () => void;
  onImported: (result: StatementResult) => void;
}) {
  const t = useT();
  const [file, setFile] = useState<Loaded | null>(null);
  const [format, setFormat] = useState<StatementFormat>("csv");
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [needsColumns, setNeedsColumns] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = async (files: File[]) => {
    const one = files[0];
    if (!one) return;
    setProblem(null);
    setNeedsColumns(false);
    setColumns({});
    const text = await one.text();
    if (text.length > MAX_CHARS) {
      setFile(null);
      setProblem(t("statement.too_big"));
      return;
    }
    const detected = formatOf(one.name, text);
    setFormat(detected);
    setFile({ name: one.name, size: one.size, text, format: detected });
  };

  const preview = file ? previewOf(file.text, format) : null;
  const chosen = Object.fromEntries(Object.entries(columns).filter(([, name]) => name !== NONE));

  const send = async () => {
    if (!file || busy) return;
    setBusy(true);
    try {
      onImported(await api.importStatement(product.key, { content: file.text, format, ...(Object.keys(chosen).length ? { columns: chosen } : {}) }));
    } catch (e) {
      const said = e instanceof Refused ? capital(e.message) : t("statement.failed");
      setProblem(said);
      setNeedsColumns(format === "csv" && e instanceof Refused && /column/i.test(e.message));
      setBusy(false);
    }
  };

  return (
    <Sheet
      title={t("statement.title", { name: product.name })}
      onClose={onBack}
      action={{ label: t("statement.import"), onClick: send, disabled: !file || !preview || preview.total === 0 || busy }}
    >
      {problem && <Hint tone="warning">{problem}</Hint>}
      <Hint>{t("statement.hint")}</Hint>
      <FileField label={t("statement.pick")} accept=".csv,.ofx,.qfx,text/csv,text/plain" hint={t("statement.formats")} onFiles={pick} />
      {file && preview && (
        <>
          <FilePreview
            name={file.name}
            size={file.size}
            columns={
              format === "ofx"
                ? [t("statement.col_date"), t("statement.col_amount"), t("statement.col_description")]
                : (preview.header ?? undefined)
            }
            rows={preview.rows}
            total={preview.total}
            onRemove={() => {
              setFile(null);
              setProblem(null);
              setNeedsColumns(false);
            }}
          />
          <Hint>{t("statement.found", { count: preview.total, format: format.toUpperCase() })}</Hint>
          {needsColumns && preview.header && (
            <>
              <Hint>{t("statement.columns_hint")}</Hint>
              {MAPPED.map((key) => (
                <SelectField<string>
                  key={key}
                  label={t(`statement.column.${key}`)}
                  value={columns[key] ?? NONE}
                  onChange={(value) => setColumns({ ...columns, [key]: value })}
                  options={[{ value: NONE, label: t("statement.column_auto") }, ...preview.header!.map((name) => ({ value: name, label: name }))]}
                />
              ))}
              <Button variant="tinted" size="small" onClick={send} disabled={busy}>
                {t("statement.try_again")}
              </Button>
            </>
          )}
        </>
      )}
    </Sheet>
  );
}
