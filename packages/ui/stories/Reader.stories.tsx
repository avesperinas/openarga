import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import {
  ArticleReader,
  BranchList,
  Button,
  Card,
  Carousel,
  ChatBubble,
  ChatText,
  ChatThread,
  Composer,
  FactCard,
  FloatButton,
  MotifBackdrop,
  PickCard,
  QuestionCard,
  ReactionBar,
  ReaderHero,
  ResourceRow,
  SectionRail,
  StreakBadge,
  TextAreaField,
  TopicChip,
  TraitRow,
  Working,
} from "../src/index";

const meta = { title: "Lectura", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const TEXT =
  "In 371 BC, on the plain of Leuctra, a Theban army broke the Spartan formation with a column fifty ranks deep on the left wing.\n\nEpaminondas massed his strength there and held the rest back, in echelon, so it would reach the clash late.";

export const Pildora: Story = {
  render: () => {
    const [reaction, setReaction] = React.useState<"interested" | "known" | "other" | null>(null);
    const [saved, setSaved] = React.useState(false);
    return (
      <div style={{ maxWidth: 390, display: "grid", gap: "1.5rem", position: "relative" }}>
        <MotifBackdrop glyph="landmark" hue={3} />
        <ReaderHero
          eyebrow="Tuesday 10 November"
          title="Your pill"
          actions={
            <>
              <StreakBadge days={6} />
              <FloatButton icon="spark" label="Surprise me" tone="accent" onClick={() => {}} />
            </>
          }
        />
        <SectionRail
          label="Secciones"
          items={[
            { id: "leer", label: "Leer", icon: "book" },
            { id: "contar", label: "To tell", icon: "lightbulb" },
            { id: "mas", label: "Learn more", icon: "arrow-right" },
            { id: "seguir", label: "Seguir", icon: "bookmark" },
          ]}
        />
        <ArticleReader
          id="leer"
          topic={<TopicChip name="Historia" glyph="landmark" hue={3} />}
          eyebrow="Because you started a novel set in ancient Greece"
          headline="The column that broke Sparta"
          lead="An army that never lost, a plain in Boeotia and an idea so simple nobody had tried it."
          sections={[
            { title: "The oblique order", text: TEXT },
            { title: "What came after", text: TEXT },
          ]}
          highlight={{ label: "To tell", text: "Sparta had not lost a pitched battle in generations.", id: "contar" }}
          coda={{ label: "To think about:", text: "Why did such a simple idea take so long to arrive?" }}
          listen={{ lang: "es-ES" }}
        >
          <ReactionBar
            label="What did you think?"
            value={reaction}
            onChange={setReaction}
            options={[
              { value: "interested", label: "Me interesa", icon: "heart" },
              { value: "known", label: "I already knew", icon: "done" },
              { value: "other", label: "Otro tema", icon: "repeat" },
            ]}
          />
        </ArticleReader>
        <BranchList
          id="mas"
          title="I want to know more about…"
          items={[
            { title: "Epaminondas", why: "The general who taught Philip of Macedon" },
            { title: "The Sacred Band", why: "150 pairs who decided battles", done: true },
            { title: "The fall of Sparta", why: "From Leuctra to irrelevance" },
          ]}
          onOpen={() => {}}
        />
        <Card title="To continue">
          <ResourceRow icon="book" title="A book about Thebes" detail="An author · 2019 · 320 pages" why="Liked military history" saved={saved} onSave={() => setSaved(!saved)} />
          <ResourceRow icon="headphones" hue={6} title="An ancient history podcast" detail="48 min" saved={false} onSave={() => {}} />
        </Card>
      </div>
    );
  },
};

export const DatosDelDia: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <Carousel label="Today's data">
        {[1, 2, 3].map((n) => (
          <FactCard
            key={n}
            index={n}
            total={3}
            hue={(n + 3) as 4 | 5 | 6}
            topic={<TopicChip name="Science and the universe" glyph="atom" hue={5} size="small" />}
            text="The light of some stars you see tonight left before writing existed."
            detail="The farthest ones visible to the naked eye are thousands of light years away."
            source={{ title: "A source", url: "https://example.org" }}
            liked={n === 1}
            known={false}
            onLike={() => {}}
            onKnown={() => {}}
          />
        ))}
      </Carousel>
    </div>
  ),
};

export const ParaTiEstaSemana: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <Carousel label="For you this week">
        <PickCard icon="book" hue={3} kind="Libro" title="A historical novel" detail="An author · 720 pages" why="You gave the previous one in the saga a 5" actions={<Button variant="primary" icon="plus">Guardar</Button>} />
        <PickCard icon="film" hue={7} kind="Film" title="A film" detail="2009 · 127 min" why="For your quantum master's: ancient science" actions={<Button icon="plus">Guardar</Button>} />
        <PickCard icon="headphones" hue={6} kind="Podcast" title="A podcast" detail="20 episodios" why="For your long bike rides" />
      </Carousel>
    </div>
  ),
};

export const Preguntas: Story = {
  render: () => (
    <div style={{ maxWidth: 390, display: "grid", gap: "1rem" }}>
      <QuestionCard
        kind="many"
        eyebrow="Let it know you"
        progress={{ done: 0, total: 12 }}
        text="What do you like to learn about?"
        why="To know which topics to bring you."
        options={[
          { value: "historia", label: "Historia" },
          { value: "ciencia", label: "Science and the universe" },
          { value: "economia", label: "Economy and money" },
        ]}
        onAnswer={() => {}}
        onSkip={() => {}}
        skipLabel="Saltar"
      />
      <QuestionCard
        kind="either"
        eyebrow="Insights te pregunta"
        text="Long sagas or self-contained novels?"
        why="You finished several sagas this year"
        options={[
          { value: "saga", label: "Sagas largas" },
          { value: "one", label: "Let them close" },
        ]}
        onAnswer={() => {}}
        onSkip={() => {}}
      />
    </div>
  ),
};

export const LoQueSabeDeTi: Story = {
  render: () => (
    <div style={{ maxWidth: 390, display: "grid", gap: "1rem" }}>
      <Card title="Is that right?">
        <TraitRow label="Long epic fantasy" stance={2} source="Seen in your reading" evidence="6 novelas, media 4,2" proposed onConfirm={() => {}} onReject={() => {}} />
        <TraitRow label="Clear explainers" stance={1} source="Seen in your notes" proposed onConfirm={() => {}} onReject={() => {}} />
      </Card>
      <Card title="What I know">
        <TraitRow label="Historia" stance={2} source="You answered it" proposed={false} onForget={() => {}} />
        <TraitRow label="Football" stance={-2} source="You said it" proposed={false} onForget={() => {}} />
      </Card>
      <Card>
        <TextAreaField label="What you want it to know about you" value="" onChange={() => {}} placeholder="What matters to you, your context…" />
      </Card>
    </div>
  ),
};

export const Conversacion: Story = {
  render: () => {
    const [draft, setDraft] = React.useState("");
    return (
      <div style={{ maxWidth: 390, display: "grid", gap: "1rem" }}>
        <ChatThread>
          <ChatBubble mine>
            <ChatText>Which book do you recommend for the trip?</ChatText>
          </ChatBubble>
          <ChatBubble mine={false}>
            <ChatText>I left you two in your library, both set where you are going.</ChatText>
          </ChatBubble>
          <ChatBubble mine={false}>
            <Working>Insights is looking at your data · 12 s</Working>
          </ChatBubble>
        </ChatThread>
        <Card>
          <Composer label="Ask it" value={draft} onChange={setDraft} onSend={() => setDraft("")} placeholder="Ask Insights…" />
        </Card>
      </div>
    );
  },
};
