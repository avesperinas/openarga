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

describe("reading to learn", () => {
  it("a text comes out in its paragraphs", () => {
    expect(render(<Prose text={"Uno.\n\nDos."} />).match(/<p>/g)).toHaveLength(2);
  });

  it("paragraphs split on lines and minutes come at 220 words", () => {
    expect(paragraphs("Uno.\n\nDos.\nTres.\n\n")).toEqual(["Uno.", "Dos.", "Tres."]);
    expect(readingMinutes("palabra ".repeat(660))).toBe(3);
    expect(readingMinutes("")).toBe(1);
  });

  it("the article carries its topic, headline, lead, sections with subheads and highlights", () => {
    const html = render(
      <ArticleReader
        id="leer"
        topic={<TopicChip name="History" glyph="landmark" hue={3} />}
        eyebrow="You go to Lisbon in three weeks"
        headline="The column that broke Sparta"
        lead="At Leuctra, a Theban army changed war."
        sections={[{ title: "The oblique order", text: "First.\n\nSecond." }]}
        highlight={{ label: "To tell", text: "A surprising fact.", id: "contar" }}
        coda={{ label: "To think about:", text: "Why did it take so long?" }}
        lang="es"
      />,
    );
    expect(html).toContain('id="leer"');
    expect(html).toContain('data-hue="3"');
    expect(html).toContain("<h1");
    expect(html).toContain("The oblique order</h2>");
    expect(html.match(/article-reader-text/g)).toHaveLength(2);
    expect(html).toContain('id="contar"');
    expect(html).toContain("To think about:");
  });

  it("the section bar shows only with two or more and marks the first", () => {
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

  it("the reactions say which one is chosen", () => {
    const html = render(
      <ReactionBar
        label="What did you think?"
        value="known"
        onChange={() => {}}
        options={[
          { value: "interested", label: "Interested", icon: "heart" },
          { value: "known", label: "I knew it", icon: "done" },
        ]}
      />,
    );
    expect(html).toContain('role="group"');
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toContain('aria-pressed="false"');
  });

  it("branches lock while one is being requested", () => {
    const html = render(
      <BranchList
        title="I want to know more about…"
        items={[
          { title: "Epaminondas", why: "El general" },
          { title: "The Sacred Band", why: "150 pairs", done: true },
        ]}
        busy={0}
        onOpen={() => {}}
      />,
    );
    expect(html).toContain('aria-busy="true"');
    expect(html.match(/disabled=""/g)).toHaveLength(2);
    expect(html).toContain('data-done="true"');
  });

  it("a resource with a cover links outside and its button says whether it is saved", () => {
    const html = render(
      <ResourceRow cover="/c.png" icon="book" title="A book" href="https://openlibrary.org/x" detail="2008 · 720 pages" saved onSave={() => {}} />,
    );
    expect(html).toContain('src="/c.png"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("A book: saved");
    const plain = render(<ResourceRow icon="headphones" hue={6} title="Un podcast" saved={false} />);
    expect(plain).toContain('data-hue="6"');
    expect(plain).not.toContain("<button");
  });

  it("a recommendation card without a cover carries its glyph and kind", () => {
    const html = render(
      <Carousel label="Para ti esta semana">
        <PickCard icon="film" hue={7} kind="Film" title="Agora" detail="2009" why="Hypatia" />
      </Carousel>,
    );
    expect(html).toContain('role="list"');
    expect(html).toContain('role="listitem"');
    expect(html).toContain("Film");
    expect(html).toContain("pick-card-glyph");
    expect(html).toContain('aria-label="Anterior"');
    expect(html).toContain('aria-label="Siguiente"');
    expect(html).toContain('tabindex="0"');
  });

  it("a fact of the day counts its position, links its source and its reactions", () => {
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
    expect(html).toContain('aria-label="Interested"');
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
  });

  it("the header, the streak, what floats and the wait", () => {
    const html = render(
      <ReaderHero
        eyebrow="Tuesday 10 November"
        title="Your pill"
        actions={
          <>
            <StreakBadge days={1} />
            <FloatButton icon="spark" label="Surprise me" tone="accent" onClick={() => {}} busy />
          </>
        }
      />,
    );
    expect(html).toContain("Streak: 1 day\"");
    expect(html).toContain('aria-label="Surprise me"');
    expect(html).toContain('aria-busy="true"');
    expect(render(<Working>Escribiendo</Working>)).toContain('role="status"');
    expect(render(<MotifBackdrop glyph="atom" hue={5} />)).toContain('aria-hidden="true"');
  });
});

describe("conocer a alguien", () => {
  it("a single-choice question answers on tap, without a continue button", () => {
    const html = render(
      <QuestionCard
        kind="one"
        text="At what time?"
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
    expect(html).toContain("Not now");
    expect(html).not.toContain("Continue");
  });

  it("multiple-choice ones check and carry Continue; the free one, its box", () => {
    const many = render(
      <QuestionCard kind="many" text="Which topics?" options={[{ value: "a", label: "A" }]} onAnswer={() => {}} />,
    );
    expect(many).toContain('aria-pressed="false"');
    expect(many).toContain("Continue");
    const free = render(<QuestionCard kind="free" text="What stayed with you?" options={[]} onAnswer={() => {}} />);
    expect(free).toContain("<textarea");
  });

  it("a proposed trait is confirmed or rejected; a confirmed one is forgotten", () => {
    const proposed = render(
      <TraitRow label="Epic fantasy" stance={2} source="Seen in your reading" evidence="6 novels" proposed onConfirm={() => {}} onReject={() => {}} />,
    );
    expect(proposed).toContain("Yes: Epic fantasy");
    expect(proposed).toContain("No: Epic fantasy");
    expect(proposed).toContain("Seen in your reading · 6 novels");
    const confirmed = render(<TraitRow label="Football" stance={-2} source="You said it" proposed={false} onForget={() => {}} />);
    expect(confirmed).toContain("Forget: Football");
    expect(confirmed).toContain('data-negative="true"');
  });

  it("the stance lights the dots on its side", () => {
    expect(render(<StanceDots stance={2} />).match(/data-on/g)).toHaveLength(2);
    expect(render(<StanceDots stance={-1} />).match(/data-on/g)).toHaveLength(1);
    expect(render(<StanceDots stance={0} />)).toContain('aria-label="Neutral"');
  });

  it("a conversation: yours marked, the text as written, and the box with its label", () => {
    expect(render(<ChatBubble mine sending><ChatText>Hola</ChatText></ChatBubble>)).toContain('data-mine="true"');
    const composer = render(<Composer label="Ask it" value="" onChange={() => {}} onSend={() => {}} />);
    expect(composer).toContain('aria-label="Ask it"');
    expect(composer).toContain("disabled");
    expect(render(<ChatFab label="Hablar con Insights" onClick={() => {}} />)).toContain("Hablar con Insights");
    const field = render(<TextAreaField label="De ti" value="x" onChange={() => {}} hint="Lo lee en cada pasada" />);
    expect(field).toContain("Lo lee en cada pasada");
  });
});
