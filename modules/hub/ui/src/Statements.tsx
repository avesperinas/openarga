import { Button, Card, Hint, List, ListRow } from "@openarga/ui";
import { useRef, useState } from "react";

import { Refused, type StatementRead, Unauthorised, signIn, uploadStatements } from "./api";

export function statementLine(read: StatementRead): string {
  if (read.problem) return read.problem;
  const parts = [read.entity, ...(read.accounts ?? [])].filter(Boolean);
  const facts = [];
  if (read.movements) facts.push(read.movements === 1 ? "1 movimiento" : `${read.movements} movimientos`);
  if (read.balances) facts.push(read.balances === 1 ? "1 saldo" : `${read.balances} saldos`);
  const fresh = read.new ? `${read.new} nuevos` : "nada nuevo";
  return `${parts.join(" · ")} · ${facts.join(" y ") || "nada"}, ${fresh}`;
}

export function StatementUpload() {
  const input = useRef<HTMLInputElement>(null);
  const [results, setResults] = useState<StatementRead[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (chosen: FileList | null) => {
    if (!chosen?.length) return;
    setBusy(true);
    setProblem(null);
    try {
      const files = await Promise.all(
        Array.from(chosen).map(async (file) => ({ name: file.name, content: await file.text() })),
      );
      setResults((await uploadStatements(files)).files);
    } catch (error) {
      if (error instanceof Unauthorised) return signIn();
      setProblem(error instanceof Refused ? error.message : "No se pudo subir. Vuelve a intentarlo.");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <Card title="Subir un extracto">
      <Hint>
        Para lo que no tiene conexión: guarda desde el navegador la página de movimientos de Renault Bank, o la posición
        global, la cartera y los movimientos de cada plan de Finizens, y súbelas aquí. Con la cartera, su valor se mueve
        cada día con el precio de sus fondos. Se leen y no se guardan; subirlas otra vez no duplica nada.
      </Hint>
      <input
        ref={input}
        type="file"
        accept=".html,.htm,text/html"
        multiple
        hidden
        onChange={(event) => void upload(event.target.files)}
      />
      <Button block icon="plus" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Leyendo…" : "Elegir las páginas"}
      </Button>
      {problem && (
        <Hint tone="warning">
          {problem}
        </Hint>
      )}
      {results && (
        <List>
          {results.map((read) => (
            <ListRow
              key={read.file}
              title={read.file}
              subtitle={statementLine(read)}
              tone={read.problem ? "warning" : undefined}
              detail={read.skipped?.length ? `${read.skipped.length} fuera` : undefined}
            />
          ))}
        </List>
      )}
    </Card>
  );
}
