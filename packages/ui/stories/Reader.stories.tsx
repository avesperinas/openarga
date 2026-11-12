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
  "En el año 371 antes de nuestra era, en la llanura de Leuctra, un ejército tebano rompió la formación espartana con una columna de cincuenta filas en el ala izquierda.\n\nEpaminondas concentró allí su fuerza y dejó el resto atrás, en escalón, para que llegara tarde al choque.";

export const Pildora: Story = {
  render: () => {
    const [reaction, setReaction] = React.useState<"interested" | "known" | "other" | null>(null);
    const [saved, setSaved] = React.useState(false);
    return (
      <div style={{ maxWidth: 390, display: "grid", gap: "1.5rem", position: "relative" }}>
        <MotifBackdrop glyph="landmark" hue={3} />
        <ReaderHero
          eyebrow="martes, 10 de noviembre"
          title="Tu píldora"
          actions={
            <>
              <StreakBadge days={6} />
              <FloatButton icon="spark" label="Sorpréndeme" tone="accent" onClick={() => {}} />
            </>
          }
        />
        <SectionRail
          label="Secciones"
          items={[
            { id: "leer", label: "Leer", icon: "book" },
            { id: "contar", label: "Para contar", icon: "lightbulb" },
            { id: "mas", label: "Saber más", icon: "arrow-right" },
            { id: "seguir", label: "Seguir", icon: "bookmark" },
          ]}
        />
        <ArticleReader
          id="leer"
          topic={<TopicChip name="Historia" glyph="landmark" hue={3} />}
          eyebrow="Porque empezaste una novela de la antigua Grecia"
          headline="La columna que rompió Esparta"
          lead="Un ejército que nunca perdía, una llanura en Beocia y una idea tan simple que nadie la había probado."
          sections={[
            { title: "El orden oblicuo", text: TEXT },
            { title: "Lo que vino después", text: TEXT },
          ]}
          highlight={{ label: "Para contar", text: "Esparta no perdía una batalla campal desde hacía generaciones.", id: "contar" }}
          coda={{ label: "Para pensar:", text: "¿Por qué una idea tan sencilla tardó tanto en llegar?" }}
          listen={{ lang: "es-ES" }}
        >
          <ReactionBar
            label="¿Qué te ha parecido?"
            value={reaction}
            onChange={setReaction}
            options={[
              { value: "interested", label: "Me interesa", icon: "heart" },
              { value: "known", label: "Ya lo sabía", icon: "done" },
              { value: "other", label: "Otro tema", icon: "repeat" },
            ]}
          />
        </ArticleReader>
        <BranchList
          id="mas"
          title="Quiero saber más sobre…"
          items={[
            { title: "Epaminondas", why: "El general que enseñó a Filipo de Macedonia" },
            { title: "El Batallón Sagrado", why: "150 parejas que decidieron batallas", done: true },
            { title: "La caída de Esparta", why: "De Leuctra a la irrelevancia" },
          ]}
          onOpen={() => {}}
        />
        <Card title="Para seguir">
          <ResourceRow icon="book" title="Un libro sobre Tebas" detail="Una autora · 2019 · 320 páginas" why="Le gustó la historia militar" saved={saved} onSave={() => setSaved(!saved)} />
          <ResourceRow icon="headphones" hue={6} title="Un podcast de historia antigua" detail="48 min" saved={false} onSave={() => {}} />
        </Card>
      </div>
    );
  },
};

export const DatosDelDia: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <Carousel label="Datos de hoy">
        {[1, 2, 3].map((n) => (
          <FactCard
            key={n}
            index={n}
            total={3}
            hue={(n + 3) as 4 | 5 | 6}
            topic={<TopicChip name="Ciencia y universo" glyph="atom" hue={5} size="small" />}
            text="La luz de algunas estrellas que ves esta noche salió antes de que existiera la escritura."
            detail="Las más lejanas a simple vista están a miles de años luz."
            source={{ title: "Una fuente", url: "https://example.org" }}
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
      <Carousel label="Para ti esta semana">
        <PickCard icon="book" hue={3} kind="Libro" title="Una novela histórica" detail="Un autor · 720 páginas" why="Le diste un 5 a la anterior de la saga" actions={<Button variant="primary" icon="plus">Guardar</Button>} />
        <PickCard icon="film" hue={7} kind="Película" title="Una película" detail="2009 · 127 min" why="Por tu máster de cuántica: la ciencia antigua" actions={<Button icon="plus">Guardar</Button>} />
        <PickCard icon="headphones" hue={6} kind="Podcast" title="Un podcast" detail="20 episodios" why="Para tus salidas largas en bici" />
      </Carousel>
    </div>
  ),
};

export const Preguntas: Story = {
  render: () => (
    <div style={{ maxWidth: 390, display: "grid", gap: "1rem" }}>
      <QuestionCard
        kind="many"
        eyebrow="Que te conozca"
        progress={{ done: 0, total: 12 }}
        text="¿De qué te gusta aprender?"
        why="Para saber qué temas traerte."
        options={[
          { value: "historia", label: "Historia" },
          { value: "ciencia", label: "Ciencia y universo" },
          { value: "economia", label: "Economía y dinero" },
        ]}
        onAnswer={() => {}}
        onSkip={() => {}}
        skipLabel="Saltar"
      />
      <QuestionCard
        kind="either"
        eyebrow="Insights te pregunta"
        text="¿Sagas largas o novelas que se cierran?"
        why="Has terminado varias sagas este año"
        options={[
          { value: "saga", label: "Sagas largas" },
          { value: "one", label: "Que se cierren" },
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
      <Card title="¿Es así?">
        <TraitRow label="Fantasía épica larga" stance={2} source="Lo vio en tus lecturas" evidence="6 novelas, media 4,2" proposed onConfirm={() => {}} onReject={() => {}} />
        <TraitRow label="Divulgación clara" stance={1} source="Lo vio en tus notas" proposed onConfirm={() => {}} onReject={() => {}} />
      </Card>
      <Card title="Lo que sé">
        <TraitRow label="Historia" stance={2} source="Lo contestaste" proposed={false} onForget={() => {}} />
        <TraitRow label="Fútbol" stance={-2} source="Lo dijiste" proposed={false} onForget={() => {}} />
      </Card>
      <Card>
        <TextAreaField label="Lo que quieres que sepa de ti" value="" onChange={() => {}} placeholder="Qué te importa, tu contexto…" />
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
            <ChatText>¿Qué libro me recomiendas para el viaje?</ChatText>
          </ChatBubble>
          <ChatBubble mine={false}>
            <ChatText>Te he dejado dos en tu biblioteca, los dos ambientados donde vas.</ChatText>
          </ChatBubble>
          <ChatBubble mine={false}>
            <Working>Insights está mirando tus datos · 12 s</Working>
          </ChatBubble>
        </ChatThread>
        <Card>
          <Composer label="Pregúntale" value={draft} onChange={setDraft} onSend={() => setDraft("")} placeholder="Pregúntale a Insights…" />
        </Card>
      </div>
    );
  },
};
