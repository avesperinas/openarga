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
import { t } from "./lang";

export const insightKey = (id: string) => `insight:${id}`;

export function Proposals({ proposals }: { proposals: Proposal[] }) {
  return (
    <Card title={t("insight.next_week")}>
      <List>
        {proposals.map((one, index) => (
          <ListRow
            key={one.what}
            title={`${index + 1}. ${one.what}`}
            subtitle={`${one.figure.label}: ${amount(one.figure.value, one.figure.unit)}, ${versus(one.figure)}. ${one.how}`}
          />
        ))}
      </List>
      <Hint>{t("insight.apply_hint")}</Hint>
    </Card>
  );
}

export function spoken(insight: Insight): string[] {
  const proposals = insight.proposals?.length
    ? [`${t("insight.next_week")}.`, ...insight.proposals.map((one, index) => `${index + 1}. ${one.what}.`)]
    : [`${t("insight.would_do")}: ${insight.action}`];
  return [insight.title, ...paragraphs(insight.body), `${t("insight.affects")}: ${insight.affects}`, ...proposals];
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
      setProblem(t("insight.rate_failed")),
    );
  };

  return (
    <Screen>
      <ScreenHeader
        eyebrow={
          insight
            ? `${insight.kind === "weekly" ? t("insight.your_week") : DOMAINS[insight.domain]} · ${when(insight.created_at)}`
            : undefined
        }
        title={insight?.title}
        back={{ label: t("inbox.title"), onClick: onBack }}
      />
      <OfflineNotice />

      {problem && <Hint tone="warning">{problem}</Hint>}
      {found.loading && <Skeleton label={t("insight.opening")} />}
      {insight === null && found.error && (
        <ErrorState title={t("insight.open_failed")} detail={found.error.message} onRetry={found.refresh} />
      )}

      {insight && (
        <>
          <ReadAloud parts={spoken(insight)} title={insight.title} />
          <Card>
            <Prose text={insight.body} />
          </Card>

          <Card title={t("insight.figures")}>
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

          <Card title={t("insight.affects")}>
            <Prose text={insight.affects} />
          </Card>

          {insight.proposals?.length ? (
            <Proposals proposals={insight.proposals} />
          ) : (
            <Card title={t("insight.would_do")}>
              <Prose text={insight.action} />
            </Card>
          )}

          <Card title={t("insight.useful")}>
            <ChoiceChips label={t("insight.rating")} options={RATINGS} value={insight.rating} onChange={rate} />
          </Card>

          <Button variant="primary" block icon="note" onClick={() => onAnswer(insight.id)}>
            Contestar
          </Button>
        </>
      )}
    </Screen>
  );
}
