import { invalidate, useResource } from "@openarga/app";
import { EmptyState, ErrorState, Notice, OfflineNotice, QuestionCard, Screen, Skeleton } from "@openarga/ui";
import { useState } from "react";

import { type Answer, type Onboarding, TASTES, TODAY, answerStart, readOnboarding } from "./api";
import { ScreenHeader, useApp } from "./Header";
import { t } from "./lang";

export function OnboardingScreen({ onBack, onDone }: { onBack: () => void; onDone: () => void }) {
  const app = useApp();
  const found = useResource("onboarding", readOnboarding);
  const [state, setState] = useState<Onboarding | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const now = state ?? found.data ?? null;
  const question = now?.questions[0];

  const reply = (answer: Answer | null) => {
    if (!question?.bank_key) return;
    setBusy(true);
    setProblem("");
    void answerStart(question.bank_key, answer)
      .then((next) => {
        setState(next);
        invalidate(TASTES);
        invalidate(TODAY);
      })
      .catch(() => setProblem(t("error.save_again")))
      .finally(() => setBusy(false));
  };

  return (
    <Screen>
      <ScreenHeader eyebrow={t("start.eyebrow", { name: app.name })} title={t("today.meet")} back={{ label: t("action.back"), onClick: onBack }} />
      <OfflineNotice />
      {problem && <Notice tone="warning">{problem}</Notice>}
      {!now && found.loading && <Skeleton label={t("start.loading")} />}
      {!now && found.error && <ErrorState title={t("start.failed")} detail={found.error.message} onRetry={found.refresh} />}
      {now && question && (
        <QuestionCard
          key={question.bank_key}
          eyebrow={t("today.meet")}
          progress={{ done: now.answered, total: now.total }}
          kind={question.kind}
          text={question.text}
          why={question.why}
          options={question.options}
          busy={busy}
          skipLabel={t("start.skip")}
          onSkip={() => reply(null)}
          onAnswer={reply}
        />
      )}
      {now && !question && (
        <EmptyState icon="done" hue={2} title={t("start.done")} action={{ label: t("start.see"), icon: "arrow-right", onClick: onDone }}>
          {t("start.done_detail")}
        </EmptyState>
      )}
    </Screen>
  );
}
