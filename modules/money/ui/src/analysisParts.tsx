import {
  Button,
  List,
  ListRow,
  Notice,
  Sheet,
  Skeleton,
  type StatTone,
  type TableColumn,
  downloadCsv,
  tableCsv,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { Unauthorised } from "./api";
import { moneyWhole, percentText, say } from "./format";

export function useLoad<T>(load: () => Promise<T>, key: string): {
  data: T | null;
  failed: "session" | "failed" | null;
  loading: boolean;
  retry: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState<"session" | "failed" | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setFailed(null);
    load().then(
      (found) => {
        if (!live) return;
        setData(found);
        setLoading(false);
      },
      (error) => {
        if (!live) return;
        setFailed(error instanceof Unauthorised ? "session" : "failed");
        setLoading(false);
      },
    );
    return () => {
      live = false;
    };
  }, [key, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { data, failed, loading, retry };
}

export function Loading<T>({
  state,
  rows = 6,
  children,
}: {
  state: { data: T | null; failed: "session" | "failed" | null; retry: () => void };
  rows?: number;
  children: (data: T) => React.ReactNode;
}) {
  if (state.failed === "session") {
    return (
      <Notice
        tone="negative"
        title={say("analysis.sign_in_again")}
        action={{ label: say("app.sign_in"), onClick: () => window.location.assign("/login") }}
      />
    );
  }
  if (state.failed) {
    return <Notice tone="negative" title={say("analysis.failed")} action={{ label: say("common.retry"), onClick: state.retry }} />;
  }
  if (!state.data) return <Skeleton rows={rows} label={say("analysis.computing")} />;
  return <>{children(state.data)}</>;
}

export function delta(
  now: number,
  before: number | null | undefined,
  against: string,
  goodUp = true,
): { text: string; tone: StatTone } {
  if (before === null || before === undefined || (before === 0 && now !== 0)) {
    return { text: contract(say("delta.no_data", { against })), tone: "neutral" };
  }
  const diff = now - before;
  if (Math.abs(diff) < 0.5) return { text: say("delta.same", { against }), tone: "neutral" };
  const pct = before !== 0 ? ` (${diff > 0 ? "+" : "−"}${percentText(Math.abs(diff / before))})` : "";
  const good = goodUp ? diff > 0 : diff < 0;
  return { text: contract(say("delta.against", { amount: `${moneyWhole(diff, true)}${pct}`, against })), tone: good ? "positive" : "negative" };
}

export function contract(text: string): string {
  return text.replace(/\ba el\b/g, "al").replace(/\bde el\b/g, "del");
}

export function signedPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return "—";
  if (Math.abs(ratio) < 0.0005) return percentText(0);
  return `${ratio > 0 ? "+" : "−"}${percentText(Math.abs(ratio))}`;
}

export function CsvButton<Row>({ name, columns, rows }: { name: string; columns: TableColumn<Row>[]; rows: Row[] }) {
  if (rows.length === 0) return null;
  return (
    <Button variant="plain" onClick={() => downloadCsv(`${name}.csv`, tableCsv(columns, rows))}>
      {say("analysis.export_csv")}
    </Button>
  );
}

export function dayText(iso: string): string {
  return iso.split("-").reverse().join("/");
}

export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  return `${d} ${months[(m ?? 1) - 1]}`;
}

export function narrowColumns<Row>(columns: TableColumn<Row>[], keys: string[]): TableColumn<Row>[] {
  return keys.flatMap((key) => columns.filter((c) => c.key === key));
}

export function RowSheet<Row>({
  title,
  columns,
  row,
  onClose,
  children,
}: {
  title: string;
  columns: TableColumn<Row>[];
  row: Row;
  onClose: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Sheet title={title} onClose={onClose}>
      <List>
        {columns.slice(1).map((c) => (
          <ListRow key={c.key} title={c.label} value={cellText(c.cell(row))} />
        ))}
      </List>
      {children}
    </Sheet>
  );
}

function cellText(value: React.ReactNode): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}
