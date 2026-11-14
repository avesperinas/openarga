import { invalidate, useResource } from "@openarga/app";
import {
  Card,
  Carousel,
  EmptyState,
  ErrorState,
  FactCard,
  FloatButton,
  IconBadge,
  MediaCard,
  Notice,
  OfflineNotice,
  QuestionCard,
  ReaderHero,
  Screen,
  Section,
  Skeleton,
  StreakBadge,
  TopicChip,
  Working,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import { type Answer, type Ask, type Fact, TASTES, TODAY, type Today, answerQuestion, askMore, reactFact, readTastes, readToday } from "./api";
import { ScreenHeader, useApp } from "./Header";
import { POLL_MS, PillReader, useAsk } from "./Pill";
import { familyOf, glyphOf, longDay } from "./taste-words";
import { DOMAIN_HUES, DOMAIN_ICONS, DOMAINS, when } from "./words";
import { t } from "./lang";

export function pillState(today: Today): "ready" | "writing" | "failed" | "later" | "off" {
  if (today.pill) return "ready";
  if (!today.settings.pill_on) return "off";
  if (today.asked?.state === "waiting") return "writing";
  if (today.asked && (today.asked.state === "failed" || today.asked.state === "refused")) return "failed";
  return "later";
}

export function TodayScreen({
  onOpenPill,
  onOpenInsight,
  onStart,
}: {
  onOpenPill: (id: string) => void;
  onOpenInsight: (id: string) => void;
  onStart: () => void;
}) {
  const app = useApp();
  const found = useResource(TODAY, readToday, { persist: true });
  const families = useResource(TASTES, readTastes, { persist: true }).data?.families ?? [];
  const today = found.data ?? null;
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState<Ask | null>(null);
  const [answering, setAnswering] = useState(false);
  const [problem, setProblem] = useState("");
  const [facts, setFacts] = useState<Record<string, Fact["reaction"]>>({});

  const [surprise] = useAsk(asked, (ready) => {
    setAsking(false);
    invalidate(TODAY);
    if (ready.pill_id) onOpenPill(ready.pill_id);
  });

  const writing = today ? pillState(today) === "writing" || today.waiting.length > 0 : false;
  useEffect(() => {
    if (!writing) return;
    const timer = window.setInterval(found.refresh, POLL_MS);
    return () => window.clearInterval(timer);
  }, [writing, found.refresh]);

  const surpriseMe = () => {
    setAsking(true);
    setProblem("");
    void askMore("surprise")
      .then(setAsked)
      .catch((error: unknown) => {
        setAsking(false);
        setProblem(error instanceof Error ? error.message : t("error.ask"));
      });
  };

  const answer = (id: string, given: Answer | null) => {
    setAnswering(true);
    void answerQuestion(id, given)
      .then(() => invalidate(TODAY))
      .catch(() => setProblem(t("error.answer")))
      .finally(() => setAnswering(false));
  };

  const react = (fact: Fact, reaction: "interested" | "known") => {
    const next = (facts[fact.id] ?? fact.reaction) === reaction ? null : reaction;
    setFacts((now) => ({ ...now, [fact.id]: next }));
    void reactFact(fact.id, next).catch(() => undefined);
  };

  return (
    <Screen>
      <ScreenHeader />
      <ReaderHero
        eyebrow={longDay(today?.day ?? new Date().toISOString())}
        title={t("today.title")}
        actions={
          <>
            {today && today.streak > 0 && <StreakBadge days={today.streak} />}
            <FloatButton icon="spark" label={t("today.surprise")} tone="accent" busy={asking} onClick={surpriseMe} />
          </>
        }
      />
      <OfflineNotice />

      {found.loading && !today && <Skeleton label={t("today.loading")} />}
      {!today && found.error && <ErrorState title={t("today.failed")} detail={found.error.message} onRetry={found.refresh} />}

      {problem && <Notice tone="warning">{problem}</Notice>}
      {surprise?.state === "waiting" && (
        <Card>
          <Working>{t("today.writing_another", { name: app.name })}</Working>
        </Card>
      )}

      {today && (
        <>
          {!today.onboarding.done && today.onboarding.answered === 0 && (
            <Notice title={t("today.meet")} action={{ label: t("today.start"), onClick: onStart }}>
              {t("today.meet_detail", { name: app.name })}
            </Notice>
          )}

          {today.question?.id && (
            <QuestionCard
              key={today.question.id}
              eyebrow={t("today.asks", { name: app.name })}
              kind={today.question.kind}
              text={today.question.text}
              why={today.question.why}
              options={today.question.options}
              busy={answering}
              onAnswer={(given) => answer(today.question!.id!, given)}
              onSkip={() => answer(today.question!.id!, null)}
            />
          )}

          {today.facts.length > 0 && (
            <Section title={t("today.facts")} count={today.facts.length}>
              <Carousel label={t("today.facts")}>
                {today.facts.map((fact, index) => {
                  const family = familyOf(families, fact.family_key);
                  const reaction = facts[fact.id] ?? fact.reaction;
                  return (
                    <FactCard
                      key={fact.id}
                      index={index + 1}
                      total={today.facts.length}
                      hue={family.hue}
                      topic={<TopicChip name={family.name} glyph={glyphOf(family)} hue={family.hue} size="small" />}
                      text={fact.text}
                      detail={fact.detail}
                      source={fact.source.url ? { title: fact.source.title ?? "Fuente", url: fact.source.url } : null}
                      liked={reaction === "interested"}
                      known={reaction === "known"}
                      onLike={() => react(fact, "interested")}
                      onKnown={() => react(fact, "known")}
                    />
                  );
                })}
              </Carousel>
            </Section>
          )}

          {today.pill ? (
            <PillReader pill={today.pill} picks={today.picks} families={families} onOpen={onOpenPill} />
          ) : (
            <PillPending today={today} name={app.name} onAsk={surpriseMe} busy={asking} />
          )}

          {today.waiting.map((one) => (
            <Card key={one.id}>
              <Working>
                {one.branch ? t("today.writing_branch", { name: app.name, branch: one.branch }) : t("today.writing_other", { name: app.name })}
              </Working>
            </Card>
          ))}

          {today.latest && (
            <Section title={t("today.latest", { name: app.name })} count={today.unread || undefined}>
              <MediaCard
                media={<IconBadge name={DOMAIN_ICONS[today.latest.domain]} hue={DOMAIN_HUES[today.latest.domain]} />}
                title={today.latest.title}
                lines={[`${today.latest.kind === "weekly" ? t("insight.your_week") : DOMAINS[today.latest.domain]} · ${when(today.latest.created_at)}`]}
                onOpen={() => onOpenInsight(today.latest!.id)}
              />
            </Section>
          )}
        </>
      )}
      <AppVersion />
    </Screen>
  );
}

function PillPending({ today, name, onAsk, busy }: { today: Today; name: string; onAsk: () => void; busy: boolean }) {
  const state = pillState(today);
  if (state === "writing") {
    return (
      <Card>
        <Working>{t("today.writing_today", { name, time: today.settings.pill_time })}</Working>
      </Card>
    );
  }
  if (state === "failed") {
    return (
      <Notice tone="warning" title={t("today.pill_failed")} action={{ label: t("today.ask_another"), onClick: onAsk }}>
        {today.asked?.detail ?? t("pill.not_written")} {t("today.retries")}
      </Notice>
    );
  }
  return (
    <EmptyState
      icon="spark"
      hue={5}
      title={state === "off" ? t("today.off") : t("today.arrives", { time: today.settings.pill_time })}
      action={busy ? undefined : { label: t("today.ask_now"), icon: "spark", onClick: onAsk }}
    >
      {t("today.pill_about", { minutes: today.settings.pill_minutes })}
    </EmptyState>
  );
}
