import { invalidate, useResource } from "@openarga/app";
import { EmptyState, ErrorState, Notice, OfflineNotice, QuestionCard, Screen, Skeleton } from "@openarga/ui";
import { useState } from "react";

import { type Answer, type Onboarding, TASTES, TODAY, answerStart, readOnboarding } from "./api";
import { ScreenHeader, useApp } from "./Header";

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
      .catch(() => setProblem("No se pudo guardar. Inténtalo otra vez."))
      .finally(() => setBusy(false));
  };

  return (
    <Screen>
      <ScreenHeader eyebrow={`${app.name} quiere conocerte`} title="Que te conozca" back={{ label: "Volver", onClick: onBack }} />
      <OfflineNotice />
      {problem && <Notice tone="warning">{problem}</Notice>}
      {!now && found.loading && <Skeleton label="Preparando las preguntas" />}
      {!now && found.error && <ErrorState title="No se pudieron abrir las preguntas" detail={found.error.message} onRetry={found.refresh} />}
      {now && question && (
        <QuestionCard
          key={question.bank_key}
          eyebrow="Que te conozca"
          progress={{ done: now.answered, total: now.total }}
          kind={question.kind}
          text={question.text}
          why={question.why}
          options={question.options}
          busy={busy}
          skipLabel="Saltar"
          onSkip={() => reply(null)}
          onAnswer={reply}
        />
      )}
      {now && !question && (
        <EmptyState icon="done" hue={2} title="Ya te conoce un poco más" action={{ label: "Ver lo que sabe de ti", icon: "arrow-right", onClick: onDone }}>
          Con esto elige tus temas, tu hora y lo que te recomienda. Lo que vaya viendo en tus lecturas, tus estudios y tus viajes te
          lo propondrá en Tú para que lo confirmes.
        </EmptyState>
      )}
    </Screen>
  );
}
