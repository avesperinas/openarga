import { invalidate, mutate, peek, useResource } from "@openarga/app";
import {
  Button,
  Card,
  ChoiceChips,
  ErrorState,
  HeadlineFigure,
  Hint,
  List,
  ListRow,
  OfflineNotice,
  Prose,
  ReadAloud,
  Screen,
  Skeleton,
  Stack,
} from "@openarga/ui";
import { useState } from "react";

import { INSIGHTS, type Insight, type Proposal, type Rating, markRead, rateInsight } from "./api";
import { ScreenHeader } from "./Header";
import { DOMAINS, RATINGS, against, amount, changeOf, paragraphs, versus, when } from "./words";

export const insightKey = (id: string) => `insight:${id}`;

export function Proposals({ proposals }: { proposals: Proposal[] }) {
  return (
    <Card title="La semana que viene">
      <List>
        {proposals.map((one, index) => (
          <ListRow
            key={one.what}
            title={`${index + 1}. ${one.what}`}
            subtitle={`${one.figure.label}: ${amount(one.figure.value, one.figure.unit)}, ${versus(one.figure)}. ${one.how}`}
          />
        ))}
      </List>
      <Hint>Para aplicar una, díselo a Claude: «aplica la 1 de la semana».</Hint>
    </Card>
  );
}

export function spoken(insight: Insight): string[] {
  const proposals = insight.proposals?.length
    ? ["La semana que viene.", ...insight.proposals.map((one, index) => `${index + 1}. ${one.what}.`)]
    : [`Qué haría: ${insight.action}`];
  return [insight.title, ...paragraphs(insight.body), `Qué afecta: ${insight.affects}`, ...proposals];
}

export function InsightScreen({
  id,
  onBack,
  onAnswer,
}: {
  id: string;
  onBack: () => void;
  onAnswer: (id: string) => void;
}) {
  const key = insightKey(id);
  const found = useResource(key, () => markRead(id).finally(() => invalidate(INSIGHTS)), {
    initial: () => peek<Insight[]>(INSIGHTS)?.find((one) => one.id === id),
  });
  const insight = found.data ?? null;
  const [problem, setProblem] = useState("");

  const rate = (rating: Rating) => {
    if (!insight) return;
    const wanted = insight.rating === rating ? null : rating;
    setProblem("");
    mutate<Insight>(key, { ...insight, rating: wanted }, { request: () => rateInsight(insight.id, wanted) }).catch(() =>
      setProblem("No se pudo guardar la valoración."),
    );
  };

  return (
    <Screen>
      <ScreenHeader
        eyebrow={
          insight
            ? `${insight.kind === "weekly" ? "Tu semana" : DOMAINS[insight.domain]} · ${when(insight.created_at)}`
            : undefined
        }
        title={insight?.title}
        back={{ label: "Consejos", onClick: onBack }}
      />
      <OfflineNotice />

      {problem && <Hint tone="warning">{problem}</Hint>}
      {found.loading && <Skeleton label="Abriendo el consejo" />}
      {insight === null && found.error && (
        <ErrorState title="No se pudo abrir el consejo" detail={found.error.message} onRetry={found.refresh} />
      )}

      {insight && (
        <>
          <ReadAloud parts={spoken(insight)} title={insight.title} />
          <Card>
            <Prose text={insight.body} />
          </Card>

          <Card title="Tus cifras">
            <Stack>
              {insight.figures.map((figure) => {
                const change = changeOf(figure);
                return (
                  <div key={figure.label}>
                    <HeadlineFigure
                      label={figure.label}
                      value={amount(figure.value, null)}
                      unit={figure.unit ?? undefined}
                      change={change ? { text: change, direction: "flat" } : undefined}
                    />
                    <Hint>{against(figure)}</Hint>
                  </div>
                );
              })}
            </Stack>
          </Card>

          <Card title="Qué afecta">
            <Prose text={insight.affects} />
          </Card>

          {insight.proposals?.length ? (
            <Proposals proposals={insight.proposals} />
          ) : (
            <Card title="Qué haría">
              <Prose text={insight.action} />
            </Card>
          )}

          <Card title="¿Te sirve?">
            <ChoiceChips label="Tu valoración" options={RATINGS} value={insight.rating} onChange={rate} />
          </Card>

          <Button variant="primary" block icon="note" onClick={() => onAnswer(insight.id)}>
            Contestar
          </Button>
        </>
      )}
    </Screen>
  );
}
