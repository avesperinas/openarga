import { invalidate, useResource } from "@openarga/app";
import {
  ArticleReader,
  BranchList,
  Card,
  ErrorState,
  List,
  ListRow,
  MotifBackdrop,
  Notice,
  OfflineNotice,
  type RailItem,
  ReactionBar,
  ResourceRow,
  Screen,
  SectionRail,
  Skeleton,
  TopicChip,
  Working,
  useReadingChrome,
} from "@openarga/ui";
import { useEffect, useRef, useState } from "react";

import {
  type Ask,
  type Family,
  PICKS,
  type Pill,
  type PillLine,
  type PillReaction,
  type Recommendation,
  TASTES,
  TODAY,
  askMore,
  audioOf,
  coverOf,
  markPillRead,
  reactPill,
  readAsk,
  readPill,
  readTastes,
  savePick,
} from "./api";
import { ScreenHeader, useApp } from "./Header";
import { KINDS, detailOf, familyOf, glyphOf } from "./taste-words";
import { currentLocale, t } from "./lang";

const REACTIONS: { value: PillReaction; label: string; icon: "heart" | "done" | "repeat" }[] = [
  { value: "interested", get label() { return t("reaction.interested"); }, icon: "heart" },
  { value: "known", get label() { return t("reaction.known"); }, icon: "done" },
  { value: "other", get label() { return t("reaction.other"); }, icon: "repeat" },
];

const VOICES: Record<string, string> = { es: "es-ES", de: "de-DE", en: "en-GB", fr: "fr-FR", it: "it-IT", eu: "eu-ES" };

export const voiceOf = (language: string) => VOICES[language] ?? language;

const ARTWORK = "/insights/icon-512.png";

export const POLL_MS = 15_000;

export function useAsk(initial: Ask | null, onReady: (ask: Ask) => void) {
  const [ask, setAsk] = useState<Ask | null>(initial);
  const ready = useRef(onReady);
  ready.current = onReady;
  useEffect(() => setAsk(initial), [initial]);
  useEffect(() => {
    if (!ask || ask.state !== "waiting") return;
    const timer = window.setInterval(() => {
      void readAsk(ask.id)
        .then((now) => {
          setAsk(now);
          if (now.state === "ready") ready.current(now);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [ask]);
  return [ask, setAsk] as const;
}

export function railOf(pill: Pill, picks: Recommendation[]): RailItem[] {
  return [
    { id: "read", label: t("pill.read"), icon: "book" as const },
    { id: "tell", label: t("pill.to_tell"), icon: "lightbulb" as const },
    ...(pill.branches.length ? [{ id: "more", label: t("pill.more"), icon: "arrow-right" as const }] : []),
    ...(picks.length ? [{ id: "follow", label: t("pill.follow"), icon: "bookmark" as const }] : []),
    ...(pill.glossary.length ? [{ id: "vocabulary", label: t("pill.vocabulary"), icon: "globe" as const }] : []),
    { id: "sources", label: t("pill.sources"), icon: "link" as const },
  ];
}

export function PillReader({
  pill,
  picks,
  descendants = [],
  families,
  onOpen,
}: {
  pill: Pill;
  picks: Recommendation[];
  descendants?: PillLine[];
  families: Family[];
  onOpen: (id: string) => void;
}) {
  const app = useApp();
  const family = familyOf(families, pill.family_key);
  const [reaction, setReaction] = useState<PillReaction | null>(pill.reaction);
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [branching, setBranching] = useState<number | null>(null);
  const [asked, setAsked] = useState<Ask | null>(null);
  const [problem, setProblem] = useState("");
  useReadingChrome();

  useEffect(() => {
    if (pill.read_at) return;
    void markPillRead(pill.id)
      .then(() => invalidate(TODAY))
      .catch(() => undefined);
  }, [pill.id, pill.read_at]);
  useEffect(() => setReaction(pill.reaction), [pill.reaction]);

  const [waiting] = useAsk(asked, (ready) => {
    setBranching(null);
    invalidate(TODAY);
    if (ready.pill_id) onOpen(ready.pill_id);
  });

  const react = (value: PillReaction | null) => {
    setReaction(value);
    void reactPill(pill.id, value)
      .then(() => invalidate(TODAY))
      .catch(() => setReaction(pill.reaction));
    if (value === "other") void more("surprise");
  };

  const more = (origin: "surprise" | "branch", index?: number) => {
    setProblem("");
    if (index !== undefined) setBranching(index);
    const branch = index !== undefined ? pill.branches[index]?.title : undefined;
    return askMore(origin, pill.id, branch)
      .then(setAsked)
      .catch((error: unknown) => {
        setBranching(null);
        setProblem(error instanceof Error ? error.message : t("error.ask"));
      });
  };

  const save = (pick: Recommendation) => {
    setSaved((now) => ({ ...now, [pick.id]: true }));
    void savePick(pick.id)
      .then(() => invalidate(PICKS))
      .catch((error: unknown) => setProblem(error instanceof Error ? error.message : t("error.save")));
  };

  const opened = new Map(descendants.map((child) => [child.topic.toLowerCase(), child.id]));
  const branches = pill.branches.map((branch) => ({ ...branch, done: opened.has(branch.title.toLowerCase()) }));

  return (
    <>
      <MotifBackdrop glyph={glyphOf(family)} hue={family.hue} />
      <SectionRail label={t("pill.parts")} items={railOf(pill, picks)} />
      <ArticleReader
        id="read"
        topic={<TopicChip name={family.name} glyph={glyphOf(family)} hue={family.hue} />}
        eyebrow={pill.hook ?? t("pill.minutes", { minutes: pill.minutes })}
        headline={pill.headline}
        lead={pill.lead}
        sections={pill.sections}
        highlight={{ label: t("pill.to_tell"), text: pill.to_tell, id: "tell" }}
        coda={pill.to_think ? { label: t("pill.to_think"), text: pill.to_think } : undefined}
        lang={pill.language !== currentLocale() ? pill.language : undefined}
        listen={{ lang: voiceOf(pill.language), audio: audioOf(pill), artwork: ARTWORK }}
      >
        <ReactionBar label={t("pill.reaction")} options={REACTIONS} value={reaction} onChange={react} />
      </ArticleReader>

      {problem && <Notice tone="warning">{problem}</Notice>}
      {waiting?.state === "waiting" && (
        <Card>
          <Working>
            {waiting.branch ? t("pill.writing_branch", { name: app.name, branch: waiting.branch }) : t("today.writing_another", { name: app.name })}
          </Working>
        </Card>
      )}
      {waiting && (waiting.state === "failed" || waiting.state === "refused") && (
        <Notice tone="warning" title={t("pill.failed")}>
          {waiting.detail ?? t("pill.not_written")}
        </Notice>
      )}

      {branches.length > 0 && (
        <BranchList
          id="more"
          title={t("pill.know_more")}
          items={branches}
          busy={branching}
          onOpen={(index) => {
            const done = opened.get(pill.branches[index]!.title.toLowerCase());
            if (done) onOpen(done);
            else void more("branch", index);
          }}
        />
      )}

      {picks.length > 0 && (
        <section id="follow" aria-label={t("pill.to_follow")}>
          <Card title={t("pill.to_follow")}>
            {picks.map((pick) => (
              <ResourceRow
                key={pick.id}
                cover={coverOf(pick)}
                icon={KINDS[pick.kind].icon}
                hue={KINDS[pick.kind].hue}
                title={pick.title}
                href={pick.links[0]?.url}
                detail={[KINDS[pick.kind].label, detailOf(pick)].filter(Boolean).join(" · ")}
                why={pick.why}
                saved={saved[pick.id] || pick.state !== "new"}
                onSave={() => save(pick)}
                saveLabel={t("pill.save")}
              />
            ))}
          </Card>
        </section>
      )}

      {pill.glossary.length > 0 && (
        <section id="vocabulary" aria-label={t("pill.vocabulary")}>
          <Card title={t("pill.vocabulary")}>
            <List>
              {pill.glossary.map((word) => (
                <ListRow key={word.word} title={word.word} subtitle={word.meaning} />
              ))}
            </List>
          </Card>
        </section>
      )}

      <section id="sources" aria-label={t("pill.sources")}>
        <Card title={t("pill.where_from")}>
          {pill.sources.map((source) => (
            <ResourceRow key={source.url} icon="link" title={source.title} href={source.url} saved={false} />
          ))}
        </Card>
      </section>
    </>
  );
}

export function PillScreen({ id, onBack, onOpen }: { id: string; onBack: () => void; onOpen: (id: string) => void }) {
  const found = useResource(`pill:${id}`, () => readPill(id));
  const families = useResource(TASTES, readTastes, { persist: true }).data?.families ?? [];
  const out = found.data;
  return (
    <Screen>
      <ScreenHeader back={{ label: out?.parent ? t("pill.previous") : t("action.back"), onClick: out?.parent ? () => onOpen(out.parent!.id) : onBack }} />
      <OfflineNotice />
      {found.loading && !out && <Skeleton label={t("pill.opening")} />}
      {!out && found.error && <ErrorState title={t("pill.open_failed")} detail={found.error.message} onRetry={found.refresh} />}
      {out && <PillReader key={out.pill.id} pill={out.pill} picks={out.picks} descendants={out.children} families={families} onOpen={onOpen} />}
    </Screen>
  );
}
