import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  ArticleReader,
  BranchList,
  Carousel,
  ChatBubble,
  ChatFab,
  ChatText,
  Composer,
  FactCard,
  FloatButton,
  MotifBackdrop,
  PickCard,
  Prose,
  QuestionCard,
  ReactionBar,
  ReaderHero,
  ResourceRow,
  SectionRail,
  StanceDots,
  StreakBadge,
  TextAreaField,
  TopicChip,
  TraitRow,
  Working,
  paragraphs,
  readingMinutes,
} from "../src/index";

const render = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("leer para aprender", () => {
  it("un texto sale en sus párrafos", () => {
    expect(render(<Prose text={"Uno.\n\nDos."} />).match(/<p>/g)).toHaveLength(2);
  });

  it("los párrafos se separan por líneas y los minutos salen a 220 palabras", () => {
    expect(paragraphs("Uno.\n\nDos.\nTres.\n\n")).toEqual(["Uno.", "Dos.", "Tres."]);
    expect(readingMinutes("palabra ".repeat(660))).toBe(3);
    expect(readingMinutes("")).toBe(1);
  });

  it("el artículo lleva su tema, titular, entradilla, secciones con ladillo y lo destacado", () => {
    const html = render(
      <ArticleReader
        id="leer"
        topic={<TopicChip name="Historia" glyph="landmark" hue={3} />}
        eyebrow="Vas a Lisboa en tres semanas"
        headline="La columna que rompió Esparta"
        lead="En Leuctra, un ejército tebano cambió la guerra."
        sections={[{ title: "El orden oblicuo", text: "Primero.\n\nSegundo." }]}
        highlight={{ label: "Para contar", text: "Un dato sorprendente.", id: "contar" }}
        coda={{ label: "Para pensar:", text: "¿Por qué tardó tanto?" }}
        lang="es"
      />,
    );
    expect(html).toContain('id="leer"');
    expect(html).toContain('data-hue="3"');
    expect(html).toContain("<h1");
    expect(html).toContain("El orden oblicuo</h2>");
    expect(html.match(/article-reader-text/g)).toHaveLength(2);
    expect(html).toContain('id="contar"');
    expect(html).toContain("Para pensar:");
  });

  it("la barra de secciones solo sale con dos o más y marca la primera", () => {
    expect(render(<SectionRail label="Secciones" items={[{ id: "a", label: "Leer", icon: "book" }]} />)).toBe("");
    const html = render(
      <SectionRail
        label="Secciones"
        items={[
          { id: "a", label: "Leer", icon: "book" },
          { id: "b", label: "Libros", icon: "bookmark" },
        ]}
      />,
    );
    expect(html).toContain('aria-label="Secciones"');
    expect(html).toContain('href="#b"');
    expect(html.match(/aria-current="location"/g)).toHaveLength(1);
  });

  it("las reacciones dicen cuál está elegida", () => {
    const html = render(
      <ReactionBar
        label="¿Qué te ha parecido?"
        value="known"
        onChange={() => {}}
        options={[
          { value: "interested", label: "Me interesa", icon: "heart" },
          { value: "known", label: "Ya lo sabía", icon: "done" },
        ]}
      />,
    );
    expect(html).toContain('role="group"');
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toContain('aria-pressed="false"');
  });

  it("las ramas se bloquean mientras se pide una", () => {
    const html = render(
      <BranchList
        title="Quiero saber más sobre…"
        items={[
          { title: "Epaminondas", why: "El general" },
          { title: "El Batallón Sagrado", why: "150 parejas", done: true },
        ]}
        busy={0}
        onOpen={() => {}}
      />,
    );
    expect(html).toContain('aria-busy="true"');
    expect(html.match(/disabled=""/g)).toHaveLength(2);
    expect(html).toContain('data-done="true"');
  });

  it("un recurso con portada enlaza fuera y su botón dice si está guardado", () => {
    const html = render(
      <ResourceRow cover="/c.png" icon="book" title="Un libro" href="https://openlibrary.org/x" detail="2008 · 720 páginas" saved onSave={() => {}} />,
    );
    expect(html).toContain('src="/c.png"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("Un libro: guardado");
    const plain = render(<ResourceRow icon="headphones" hue={6} title="Un podcast" saved={false} />);
    expect(plain).toContain('data-hue="6"');
    expect(plain).not.toContain("<button");
  });

  it("una recomendación en tarjeta sin portada lleva su glifo y su tipo", () => {
    const html = render(
      <Carousel label="Para ti esta semana">
        <PickCard icon="film" hue={7} kind="Película" title="Ágora" detail="2009" why="Hipatia" />
      </Carousel>,
    );
    expect(html).toContain('role="list"');
    expect(html).toContain('role="listitem"');
    expect(html).toContain("Película");
    expect(html).toContain("pick-card-glyph");
    expect(html).toContain('aria-label="Anterior"');
    expect(html).toContain('aria-label="Siguiente"');
    expect(html).toContain('tabindex="0"');
  });

  it("un dato del día cuenta su posición, enlaza su fuente y sus reacciones", () => {
    const html = render(
      <FactCard
        index={2}
        total={5}
        text="Un dato cierto."
        detail="Por esto."
        hue={5}
        source={{ title: "Fuente", url: "https://example.org" }}
        liked
        known={false}
        onLike={() => {}}
        onKnown={() => {}}
      />,
    );
    expect(html).toContain("2 de 5");
    expect(html).toContain("<details");
    expect(html).toContain('href="https://example.org"');
    expect(html).toContain('<span class="fact-card-source-name">Fuente</span>');
    expect(html).toContain('aria-label="Me interesa"');
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
  });

  it("la cabecera, la racha, lo que flota y la espera", () => {
    const html = render(
      <ReaderHero
        eyebrow="martes, 10 de noviembre"
        title="Tu píldora"
        actions={
          <>
            <StreakBadge days={1} />
            <FloatButton icon="spark" label="Sorpréndeme" tone="accent" onClick={() => {}} busy />
          </>
        }
      />,
    );
    expect(html).toContain("Racha: 1 día\"");
    expect(html).toContain('aria-label="Sorpréndeme"');
    expect(html).toContain('aria-busy="true"');
    expect(render(<Working>Escribiendo</Working>)).toContain('role="status"');
    expect(render(<MotifBackdrop glyph="atom" hue={5} />)).toContain('aria-hidden="true"');
  });
});

describe("conocer a alguien", () => {
  it("una pregunta de una opción contesta al tocar, sin botón de seguir", () => {
    const html = render(
      <QuestionCard
        kind="one"
        text="¿A qué hora?"
        why="Para avisarte"
        options={[
          { value: "9", label: "9:00" },
          { value: "21", label: "21:30" },
        ]}
        onAnswer={() => {}}
        onSkip={() => {}}
        eyebrow="Insights te pregunta"
        progress={{ done: 2, total: 12 }}
      />,
    );
    expect(html).toContain("<h2");
    expect(html).toContain("Para avisarte");
    expect(html).toContain("3 de 12");
    expect(html).toContain("Ahora no");
    expect(html).not.toContain("Seguir");
  });

  it("las de varias marcan y llevan Seguir; la libre, su cuadro", () => {
    const many = render(
      <QuestionCard kind="many" text="¿Qué temas?" options={[{ value: "a", label: "A" }]} onAnswer={() => {}} />,
    );
    expect(many).toContain('aria-pressed="false"');
    expect(many).toContain("Seguir");
    const free = render(<QuestionCard kind="free" text="¿Qué te marcó?" options={[]} onAnswer={() => {}} />);
    expect(free).toContain("<textarea");
  });

  it("un rasgo propuesto se confirma o descarta; uno confirmado se olvida", () => {
    const proposed = render(
      <TraitRow label="Fantasía épica" stance={2} source="Lo vio en tus lecturas" evidence="6 novelas" proposed onConfirm={() => {}} onReject={() => {}} />,
    );
    expect(proposed).toContain("Sí: Fantasía épica");
    expect(proposed).toContain("No: Fantasía épica");
    expect(proposed).toContain("Lo vio en tus lecturas · 6 novelas");
    const confirmed = render(<TraitRow label="Fútbol" stance={-2} source="Lo dijiste" proposed={false} onForget={() => {}} />);
    expect(confirmed).toContain("Olvidar: Fútbol");
    expect(confirmed).toContain('data-negative="true"');
  });

  it("la postura enciende los puntos de su lado", () => {
    expect(render(<StanceDots stance={2} />).match(/data-on/g)).toHaveLength(2);
    expect(render(<StanceDots stance={-1} />).match(/data-on/g)).toHaveLength(1);
    expect(render(<StanceDots stance={0} />)).toContain('aria-label="Neutro"');
  });

  it("una conversación: lo tuyo marcado, lo escrito tal cual, y el cuadro con su etiqueta", () => {
    expect(render(<ChatBubble mine sending><ChatText>Hola</ChatText></ChatBubble>)).toContain('data-mine="true"');
    const composer = render(<Composer label="Pregúntale" value="" onChange={() => {}} onSend={() => {}} />);
    expect(composer).toContain('aria-label="Pregúntale"');
    expect(composer).toContain("disabled");
    expect(render(<ChatFab label="Hablar con Insights" onClick={() => {}} />)).toContain("Hablar con Insights");
    const field = render(<TextAreaField label="De ti" value="x" onChange={() => {}} hint="Lo lee en cada pasada" />);
    expect(field).toContain("Lo lee en cada pasada");
  });
});
