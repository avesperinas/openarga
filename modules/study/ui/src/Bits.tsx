import { invalidate, mutate, useResource } from "@openarga/app";
import { Badge, EmptyState, ErrorState, Hint, type IconName, Skeleton } from "@openarga/ui";
import { type CSSProperties, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { type Grade, type Tone, Unauthorised, signIn } from "./api";
import { grade as gradeText, needed, percent, verdictLabel, verdictTone } from "./words";
import { t } from "./lang";

export const changed = () => invalidate("");

const GONE = ["no existe", "does not exist"];

const gone = (error: Error | null) => GONE.some((one) => error?.message.startsWith(one));

function useOwnRead<T>(active: boolean, load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const loader = useRef(load);
  loader.current = load;

  const refresh = useCallback(async () => {
    try {
      setData(await loader.current());
      setError(null);
    } catch (reason) {
      if (reason instanceof Unauthorised) return signIn();
      setError(reason instanceof Error ? reason : new Error(t("error.something")));
    }
  }, []);

  useEffect(() => {
    if (active) void refresh();
  }, [active, refresh]);

  return { data, setData, error, refresh };
}

export function useLoad<T>(key: string, load: () => Promise<T>, { fresh = false }: { fresh?: boolean } = {}) {
  const shared = useResource(fresh ? null : key, load, { persist: true });
  const own = useOwnRead(fresh, load);
  const [problem, setProblem] = useState("");

  const fail = useCallback((error: unknown) => {
    if (error instanceof Unauthorised) return signIn();
    setProblem(error instanceof Error ? error.message : t("error.something"));
  }, []);

  const setOwn = own.setData;
  const setData = useCallback(
    (next: T | ((current: T | null) => T | null)) => {
      const apply = (current: T | null) =>
        typeof next === "function" ? (next as (current: T | null) => T | null)(current) : next;
      if (fresh) return setOwn((current) => apply(current) ?? current);
      void mutate<T>(key, (current) => apply(current ?? null) ?? current!);
    },
    [fresh, key, setOwn],
  );

  const found = fresh ? { error: own.error, refresh: own.refresh } : { error: shared.error, refresh: shared.refresh };
  const data = fresh ? own.data : (shared.data ?? null);
  return {
    data: gone(found.error) ? null : data,
    found,
    setData,
    problem,
    setProblem,
    fail,
    refresh: () => {
      changed();
      if (fresh) void own.refresh();
    },
  };
}

export function Pending({ found, what = "Study" }: { found: { error: Error | null; refresh: () => Promise<void> }; what?: string }) {
  if (!found.error) return <Skeleton rows={4} />;
  if (gone(found.error)) {
    return (
      <EmptyState icon="search" title={t("gone.title")}>
        <p>{t("gone.detail")}</p>
      </EmptyState>
    );
  }
  return <ErrorState title={t("error.no_answer", { what })} detail={found.error.message} onRetry={() => void found.refresh()} />;
}

export function Problem({ text }: { text: string }) {
  if (!text) return null;
  return <Hint tone="warning">{text}</Hint>;
}

export function Loading() {
  return <Skeleton rows={4} />;
}

export { Section } from "@openarga/ui";

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: IconName }) {
  return (
    <EmptyState title={title} icon={icon}>
      {children}
    </EmptyState>
  );
}

export function VerdictChip({ verdict }: { verdict: Grade["verdict"] }) {
  return (
    <Badge tone={verdictTone(verdict)}>{verdictLabel(verdict)}</Badge>
  );
}

export function GradeMeter({
  grade,
  scale,
  passMark,
  tone,
}: {
  grade: Grade;
  scale: number;
  passMark: number;
  tone: Tone;
}) {
  const pct = (value: number) => `${(Math.max(0, Math.min(value, scale)) / scale) * 100}%`;
  const secured = Math.max(0, Math.min(grade.secured ?? 0, scale));
  const open = (scale * grade.remaining_weight) / 100;
  const ceiling = Math.min(secured + open, scale);
  const final = grade.final;
  const big = final ?? grade.current;
  const label =
    grade.final_source === "record"
      ? t("meter.record")
      : grade.final_source === "computed"
        ? t("meter.final")
        : grade.current !== null
          ? t("meter.so_far", { percent: percent(grade.graded_weight) })
          : t("meter.no_grades");
  return (
    <div className="study-meter" data-tone={tone} data-verdict={verdictTone(grade.verdict)}>
      <div className="study-meter-head">
        <div>
          <p className="study-meter-label">{label}</p>
          <p className="study-meter-value">
            {gradeText(big, scale)}
            <span className="study-meter-scale"> / {gradeText(scale, 100)}</span>
          </p>
        </div>
        <VerdictChip verdict={grade.verdict} />
      </div>
      <div
        className="study-meter-bar"
        role="img"
        aria-label={t("meter.secured_of", { secured: gradeText(secured, scale), scale: gradeText(scale, 100) })}
        style={{ "--secured": pct(secured), "--ceiling": pct(ceiling), "--pass": pct(passMark), "--target": pct(grade.target ?? 0) } as CSSProperties}
      >
        <span className="study-meter-open" />
        <span className="study-meter-fill" />
        <span className="study-meter-pass" />
        {grade.target !== null && <span className="study-meter-target" />}
      </div>
      <div className="study-meter-legend">
        <span>
          <span className="study-key" data-key="fill" /> {t("meter.secured")} {gradeText(grade.secured ?? 0, scale)}
        </span>
        {grade.remaining_weight > 0 && (
          <span>
            <span className="study-key" data-key="open" /> {t("meter.in_play")} {percent(grade.remaining_weight)}
          </span>
        )}
        <span>
          <span className="study-key" data-key="pass" /> {t("meter.pass_mark")} {gradeText(passMark, scale)}
        </span>
      </div>
      <p className="study-meter-sentence">{grade.sentence}</p>
      {grade.unweighted > 0 && (
        <p className="study-muted">
          {t(grade.unweighted === 1 ? "meter.unweighted.one" : "meter.unweighted.other", { count: grade.unweighted })}
        </p>
      )}
    </div>
  );
}

export function neededLine(g: Grade, scale: number): string | null {
  if (g.verdict !== "in_progress") return null;
  if (g.needed_to_pass === null) return null;
  return t("grade.needed_left", { grade: needed(g.needed_to_pass, scale) });
}

export function ProgressBar({ ratio, tone, label }: { ratio: number; tone: Tone; label: string }) {
  return (
    <span
      className="study-progress"
      data-tone={tone}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(ratio * 100)}
      style={{ "--ratio": `${Math.max(0, Math.min(1, ratio)) * 100}%` } as CSSProperties}
    />
  );
}

export const rowTone = (tone: "positive" | "warning" | "negative" | "neutral") => (tone === "neutral" ? undefined : tone);

export const dueTone = (daysLeft: number) =>
  daysLeft < 0 ? ("negative" as const) : daysLeft <= 2 ? ("warning" as const) : undefined;
