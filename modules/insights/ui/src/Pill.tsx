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

const REACTIONS: { value: PillReaction; label: string; icon: "heart" | "done" | "repeat" }[] = [
  { value: "interested", label: "Me interesa", icon: "heart" },
  { value: "known", label: "Ya lo sabía", icon: "done" },
  { value: "other", label: "Otro tema", icon: "repeat" },
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
    { id: "leer", label: "Leer", icon: "book" as const },
    { id: "contar", label: "Para contar", icon: "lightbulb" as const },
    ...(pill.branches.length ? [{ id: "mas", label: "Saber más", icon: "arrow-right" as const }] : []),
    ...(picks.length ? [{ id: "seguir", label: "Seguir", icon: "bookmark" as const }] : []),
    ...(pill.glossary.length ? [{ id: "vocabulario", label: "Vocabulario", icon: "globe" as const }] : []),
    { id: "fuentes", label: "Fuentes", icon: "link" as const },
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
        setProblem(error instanceof Error ? error.message : "No se pudo pedir.");
      });
  };

  const save = (pick: Recommendation) => {
    setSaved((now) => ({ ...now, [pick.id]: true }));
    void savePick(pick.id)
      .then(() => invalidate(PICKS))
      .catch((error: unknown) => setProblem(error instanceof Error ? error.message : "No se pudo guardar."));
  };

  const opened = new Map(descendants.map((child) => [child.topic.toLowerCase(), child.id]));
  const branches = pill.branches.map((branch) => ({ ...branch, done: opened.has(branch.title.toLowerCase()) }));

  return (
    <>
      <MotifBackdrop glyph={glyphOf(family)} hue={family.hue} />
      <SectionRail label="Partes de la píldora" items={railOf(pill, picks)} />
      <ArticleReader
        id="leer"
        topic={<TopicChip name={family.name} glyph={glyphOf(family)} hue={family.hue} />}
        eyebrow={pill.hook ?? `${pill.minutes} min de lectura`}
        headline={pill.headline}
        lead={pill.lead}
        sections={pill.sections}
        highlight={{ label: "Para contar", text: pill.to_tell, id: "contar" }}
        coda={pill.to_think ? { label: "Para pensar:", text: pill.to_think } : undefined}
        lang={pill.language !== "es" ? pill.language : undefined}
        listen={{ lang: voiceOf(pill.language), audio: audioOf(pill), artwork: ARTWORK }}
      >
        <ReactionBar label="¿Qué te ha parecido?" options={REACTIONS} value={reaction} onChange={react} />
      </ArticleReader>

      {problem && <Notice tone="warning">{problem}</Notice>}
      {waiting?.state === "waiting" && (
        <Card>
          <Working>
            {app.name} está escribiendo {waiting.branch ? `«${waiting.branch}»` : "otra píldora"}: llega en uno o dos minutos y
            te avisa
          </Working>
        </Card>
      )}
      {waiting && (waiting.state === "failed" || waiting.state === "refused") && (
        <Notice tone="warning" title="No ha salido">
          {waiting.detail ?? "Tu Claude no pudo escribirla."}
        </Notice>
      )}

      {branches.length > 0 && (
        <BranchList
          id="mas"
          title="Quiero saber más sobre…"
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
        <section id="seguir" aria-label="Para seguir">
          <Card title="Para seguir">
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
                saveLabel="Guardar en tu biblioteca"
              />
            ))}
          </Card>
        </section>
      )}

      {pill.glossary.length > 0 && (
        <section id="vocabulario" aria-label="Vocabulario">
          <Card title="Vocabulario">
            <List>
              {pill.glossary.map((word) => (
                <ListRow key={word.word} title={word.word} subtitle={word.meaning} />
              ))}
            </List>
          </Card>
        </section>
      )}

      <section id="fuentes" aria-label="Fuentes">
        <Card title="De dónde sale">
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
      <ScreenHeader back={{ label: out?.parent ? "La anterior" : "Volver", onClick: out?.parent ? () => onOpen(out.parent!.id) : onBack }} />
      <OfflineNotice />
      {found.loading && !out && <Skeleton label="Abriendo la píldora" />}
      {!out && found.error && <ErrorState title="No se pudo abrir la píldora" detail={found.error.message} onRetry={found.refresh} />}
      {out && <PillReader key={out.pill.id} pill={out.pill} picks={out.picks} descendants={out.children} families={families} onOpen={onOpen} />}
    </Screen>
  );
}
