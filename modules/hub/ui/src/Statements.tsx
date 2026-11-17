import { Button, Card, Hint, List, ListRow, regional } from "@openarga/ui";
import { useRef, useState } from "react";

import { Refused, type StatementRead, Unauthorised, signIn, uploadStatements } from "./api";
import { say } from "./words";

export function statementLine(read: StatementRead): string {
  if (read.problem) return read.problem;
  const parts = [read.entity, ...(read.accounts ?? [])].filter(Boolean);
  const facts = [];
  if (read.movements) facts.push(say(read.movements === 1 ? "statements.movement" : "statements.movements", { n: read.movements }));
  if (read.balances) facts.push(say(read.balances === 1 ? "statements.balance" : "statements.balances", { n: read.balances }));
  const fresh = read.new ? say("statements.new", { n: read.new }) : say("statements.nothing_new");
  const summary = facts.length ? new Intl.ListFormat(regional().locale, { type: "conjunction" }).format(facts) : say("statements.nothing");
  return `${parts.join(" · ")} · ${summary}, ${fresh}`;
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
      setProblem(error instanceof Refused ? error.message : say("statements.failed"));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <Card title={say("statements.title")}>
      <Hint>{say("statements.hint")}</Hint>
      <input
        ref={input}
        type="file"
        accept=".html,.htm,text/html"
        multiple
        hidden
        onChange={(event) => void upload(event.target.files)}
      />
      <Button block icon="plus" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? say("statements.reading") : say("statements.choose")}
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
              detail={read.skipped?.length ? say("statements.skipped", { n: read.skipped.length }) : undefined}
            />
          ))}
        </List>
      )}
    </Card>
  );
}
