"use client";

import * as React from "react";

import { Icon, type IconName } from "./icons";
import { ReadAloud, type SpokenAudio } from "./speech";
import { say } from "./words";

export type ReaderHue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export interface TopicChipProps {
  name: string;
  glyph: IconName;
  hue: ReaderHue;
  size?: "regular" | "small";
}

export function TopicChip({ name, glyph, hue, size = "regular" }: TopicChipProps) {
  return (
    <span className="topic-chip" data-hue={hue} data-size={size}>
      <span className="topic-chip-glyph" aria-hidden="true">
        <Icon name={glyph} />
      </span>
      <span className="topic-chip-name">{name}</span>
    </span>
  );
}

const MOTIF: [number, number, number, number][] = [
  [-6, 4, 7, -18],
  [72, 2, 4, 14],
  [80, 30, 7.5, -8],
  [-8, 46, 5.5, 22],
  [64, 62, 4.5, -24],
  [6, 78, 7.5, 10],
  [76, 88, 5.5, 18],
];

export function MotifBackdrop({ glyph, hue }: { glyph: IconName; hue: ReaderHue }) {
  return (
    <div className="motif-backdrop" data-hue={hue} aria-hidden="true">
      {MOTIF.map(([x, y, size, turn], index) => (
        <span
          key={index}
          className="motif-backdrop-glyph"
          style={{ "--x": `${x}%`, "--y": `${y}%`, "--size": `${size}rem`, "--turn": `${turn}deg` } as React.CSSProperties}
        >
          <Icon name={glyph} />
        </span>
      ))}
    </div>
  );
}

export interface ArticleSection {
  title: string;
  text: string;
}

export interface ArticleReaderProps {
  id?: string;
  topic?: React.ReactNode;
  eyebrow?: string;
  headline: string;
  lead: string;
  sections: ArticleSection[];
  highlight?: { label: string; text: string; id?: string };
  coda?: { label: string; text: string };
  lang?: string;
  listen?: { lang: string; audio?: SpokenAudio | null; artwork?: string };
  children?: React.ReactNode;
}

export function paragraphs(text: string): string[] {
  return text
    .split(/\n\s*\n|\n/)
    .map((one) => one.trim())
    .filter(Boolean);
}

export function readingMinutes(...texts: string[]): number {
  const words = texts.join(" ").split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(words / 220));
}

export function spokenParts({ headline, lead, sections, highlight, coda }: Pick<ArticleReaderProps, "headline" | "lead" | "sections" | "highlight" | "coda">): string[] {
  return [
    headline,
    lead,
    ...sections.flatMap((section) => [section.title, ...paragraphs(section.text)]),
    ...(highlight ? [`${highlight.label}. ${highlight.text}`] : []),
    ...(coda ? [`${coda.label} ${coda.text}`] : []),
  ];
}

export function ArticleReader({ id, topic, eyebrow, headline, lead, sections, highlight, coda, lang, listen, children }: ArticleReaderProps) {
  const [speaking, setSpeaking] = React.useState<number | null>(null);
  const parts = React.useMemo(
    () => spokenParts({ headline, lead, sections, highlight, coda }),
    [headline, lead, sections, highlight, coda],
  );
  let at = 2;
  const on = (part: number) => (speaking === part ? true : undefined);
  return (
    <article className="article-reader" id={id} lang={lang}>
      {(topic || eyebrow) && (
        <div className="article-reader-top">
          {topic}
          {eyebrow && <p className="article-reader-eyebrow">{eyebrow}</p>}
        </div>
      )}
      <h1 className="article-reader-headline" data-speaking={on(0)}>
        {headline}
      </h1>
      {listen && (
        <ReadAloud parts={parts} lang={listen.lang} title={headline} onPart={setSpeaking} audio={listen.audio} artwork={listen.artwork} />
      )}
      <p className="article-reader-lead" data-speaking={on(1)}>
        {lead}
      </p>
      {sections.map((section, index) => {
        const title = at++;
        return (
          <section key={index} className="article-reader-section">
            <h2 className="article-reader-subhead" data-speaking={on(title)}>
              {section.title}
            </h2>
            {paragraphs(section.text).map((paragraph, number) => {
              const mine = at++;
              return (
                <p key={number} className="article-reader-text" data-speaking={on(mine)}>
                  {paragraph}
                </p>
              );
            })}
          </section>
        );
      })}
      {highlight && (
        <aside className="article-reader-highlight" id={highlight.id} data-speaking={on(at++)}>
          <span className="article-reader-highlight-label">
            <Icon name="lightbulb" />
            {highlight.label}
          </span>
          <p>{highlight.text}</p>
        </aside>
      )}
      {coda && (
        <p className="article-reader-coda" data-speaking={on(at++)}>
          <strong>{coda.label}</strong> {coda.text}
        </p>
      )}
      {children}
    </article>
  );
}

export interface RailItem {
  id: string;
  label: string;
  icon: IconName;
}

const reduced = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function jumpTo(id: string) {
  const target = typeof document === "undefined" ? null : document.getElementById(id);
  target?.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
}

export function SectionRail({ items, label }: { items: RailItem[]; label: string }) {
  const [active, setActive] = React.useState(items[0]?.id ?? "");
  const rail = React.useRef<HTMLElement>(null);

  React.useEffect(() => {
    if (typeof window === "undefined" || typeof IntersectionObserver === "undefined") return;
    const seen = new Map<string, boolean>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) seen.set(entry.target.id, entry.isIntersecting);
        const first = items.find((item) => seen.get(item.id));
        if (first) setActive(first.id);
      },
      { rootMargin: "-20% 0px -60% 0px" },
    );
    for (const item of items) {
      const target = document.getElementById(item.id);
      if (target) observer.observe(target);
    }
    return () => observer.disconnect();
  }, [items]);

  React.useEffect(() => {
    const bar = rail.current;
    const chip = bar?.querySelector<HTMLElement>(`[data-rail="${active}"]`);
    if (!bar || !chip || typeof bar.scrollTo !== "function") return;
    const left = chip.offsetLeft - (bar.clientWidth - chip.offsetWidth) / 2;
    bar.scrollTo({ left: Math.max(0, left), behavior: reduced() ? "auto" : "smooth" });
  }, [active]);

  if (items.length < 2) return null;
  return (
    <nav className="section-rail glass" aria-label={label} ref={rail}>
      {items.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          data-rail={item.id}
          className="section-rail-item"
          aria-current={item.id === active ? "location" : undefined}
          onClick={(event) => {
            event.preventDefault();
            setActive(item.id);
            jumpTo(item.id);
          }}
        >
          <Icon name={item.icon} />
          {item.label}
        </a>
      ))}
    </nav>
  );
}

export function useReadingChrome(enabled = true) {
  React.useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    const root = document.documentElement;
    let last = window.scrollY;
    const onScroll = () => {
      const now = window.scrollY;
      if (Math.abs(now - last) < 8) return;
      if (now > last && now > 160) root.dataset.reading = "away";
      else root.removeAttribute("data-reading");
      last = now;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      root.removeAttribute("data-reading");
    };
  }, [enabled]);
}

export interface ReactionOption<T extends string> {
  value: T;
  label: string;
  icon: IconName;
}

export function ReactionBar<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: ReactionOption<T>[];
  value: T | null;
  onChange: (value: T | null) => void;
}) {
  return (
    <div className="reaction-bar" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className="reaction-bar-item"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value === value ? null : option.value)}
        >
          <Icon name={option.icon} />
          {option.label}
        </button>
      ))}
    </div>
  );
}

export interface Branch {
  title: string;
  why: string;
  done?: boolean;
}

export function BranchList({
  id,
  title,
  items,
  onOpen,
  busy,
}: {
  id?: string;
  title: string;
  items: Branch[];
  onOpen: (index: number) => void;
  busy?: number | null;
}) {
  return (
    <section className="branch-list" id={id} aria-label={title}>
      <h2 className="branch-list-title">{title}</h2>
      {items.map((item, index) => (
        <button
          key={index}
          type="button"
          className="branch-list-item"
          data-done={item.done || undefined}
          aria-busy={busy === index || undefined}
          disabled={busy !== null && busy !== undefined}
          onClick={() => onOpen(index)}
        >
          <span className="branch-list-text">
            <strong>{item.title}</strong>
            <small>{item.why}</small>
          </span>
          <span className="branch-list-arrow" aria-hidden="true">
            <Icon name={item.done ? "done" : "arrow-right"} />
          </span>
        </button>
      ))}
    </section>
  );
}

export interface ResourceRowProps {
  cover?: string | null;
  icon: IconName;
  hue?: ReaderHue;
  title: string;
  href?: string | null;
  detail?: string;
  why?: string;
  saved: boolean;
  onSave?: () => void;
  saveLabel?: string;
  action?: React.ReactNode;
}

export function ResourceRow({ cover, icon, hue = 8, title, href, detail, why, saved, onSave, saveLabel = "Guardar", action }: ResourceRowProps) {
  return (
    <div className="resource-row">
      {cover ? (
        <img className="resource-row-cover" src={cover} alt="" loading="lazy" />
      ) : (
        <span className="resource-row-icon" data-hue={hue} aria-hidden="true">
          <Icon name={icon} />
        </span>
      )}
      <span className="resource-row-text">
        {href ? (
          <a className="resource-row-title" href={href} target="_blank" rel="noopener noreferrer">
            {title}
          </a>
        ) : (
          <strong className="resource-row-title">{title}</strong>
        )}
        {detail && <small className="resource-row-detail">{detail}</small>}
        {why && <small className="resource-row-why">{why}</small>}
      </span>
      {onSave && (
        <button
          type="button"
          className="resource-row-save"
          aria-pressed={saved}
          aria-label={saved ? `${title}: guardado` : `${saveLabel}: ${title}`}
          onClick={onSave}
        >
          <Icon name={saved ? "done" : "plus"} />
        </button>
      )}
      {action && <span className="resource-row-action">{action}</span>}
    </div>
  );
}

export interface PickCardProps {
  cover?: string | null;
  icon: IconName;
  hue: ReaderHue;
  kind: string;
  title: string;
  detail?: string;
  why: string;
  actions?: React.ReactNode;
}

export function PickCard({ cover, icon, hue, kind, title, detail, why, actions }: PickCardProps) {
  return (
    <article className="pick-card" data-hue={hue}>
      <div className="pick-card-media">
        {cover ? (
          <img src={cover} alt="" loading="lazy" />
        ) : (
          <span className="pick-card-glyph" aria-hidden="true">
            <Icon name={icon} />
          </span>
        )}
        <span className="pick-card-kind">{kind}</span>
      </div>
      <div className="pick-card-body">
        <h3 className="pick-card-title">{title}</h3>
        {detail && <p className="pick-card-detail">{detail}</p>}
        <p className="pick-card-why">{why}</p>
      </div>
      {actions && <div className="pick-card-actions">{actions}</div>}
    </article>
  );
}

export function Carousel({ label, children }: { label: string; children: React.ReactNode }) {
  const track = React.useRef<HTMLDivElement>(null);
  const [edges, setEdges] = React.useState({ start: true, end: true });

  const measure = React.useCallback(() => {
    const el = track.current;
    if (!el) return;
    setEdges({ start: el.scrollLeft <= 4, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 4 });
  }, []);

  React.useEffect(() => {
    const el = track.current;
    if (!el) return;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      el.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [measure, children]);

  const step = (direction: 1 | -1) => {
    const el = track.current;
    const item = el?.querySelector<HTMLElement>(".carousel-item");
    if (!el || !item || typeof el.scrollBy !== "function") return;
    const gap = parseFloat(getComputedStyle(el).columnGap || "0") || 0;
    el.scrollBy({ left: direction * (item.offsetWidth + gap), behavior: reduced() ? "auto" : "smooth" });
  };

  return (
    <div className="carousel-frame">
      <button type="button" className="carousel-arrow" data-side="start" aria-label="Anterior" hidden={edges.start} onClick={() => step(-1)}>
        <Icon name="chevron-left" />
      </button>
      <div
        className="carousel"
        role="list"
        aria-label={label}
        ref={track}
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight") {
            event.preventDefault();
            step(1);
          } else if (event.key === "ArrowLeft") {
            event.preventDefault();
            step(-1);
          }
        }}
      >
        {React.Children.map(children, (child) =>
          child ? (
            <div className="carousel-item" role="listitem">
              {child}
            </div>
          ) : null,
        )}
      </div>
      <button type="button" className="carousel-arrow" data-side="end" aria-label="Siguiente" hidden={edges.end} onClick={() => step(1)}>
        <Icon name="chevron-right" />
      </button>
    </div>
  );
}

export interface FactCardProps {
  index: number;
  total: number;
  text: string;
  detail?: string | null;
  topic?: React.ReactNode;
  hue: ReaderHue;
  source?: { title: string; url: string } | null;
  liked: boolean;
  known: boolean;
  onLike?: () => void;
  onKnown?: () => void;
}

export function FactCard({ index, total, text, detail, topic, hue, source, liked, known, onLike, onKnown }: FactCardProps) {
  return (
    <article className="fact-card" data-hue={hue}>
      <div className="fact-card-top">
        {topic}
        <span className="fact-card-count">
          {index} de {total}
        </span>
      </div>
      <p className="fact-card-text">{text}</p>
      {detail && (
        <details className="fact-card-more">
          <summary>{say("fact.why")}</summary>
          <p>{detail}</p>
        </details>
      )}
      <div className="fact-card-foot">
        {source && (
          <a className="fact-card-source" href={source.url} target="_blank" rel="noopener noreferrer">
            <Icon name="link" />
            <span className="fact-card-source-name">{source.title}</span>
          </a>
        )}
        <span className="fact-card-actions">
          {onLike && (
            <button type="button" className="fact-card-react" aria-pressed={liked} aria-label={say("fact.interested")} onClick={onLike}>
              <Icon name="heart" />
            </button>
          )}
          {onKnown && (
            <button type="button" className="fact-card-react" aria-pressed={known} aria-label={say("fact.known")} onClick={onKnown}>
              <Icon name="done" />
            </button>
          )}
        </span>
      </div>
    </article>
  );
}

export function StreakBadge({ days }: { days: number }) {
  return (
    <span className="streak-badge glass" role="img" aria-label={days === 1 ? say("streak.one") : say("streak.other", { count: days })}>
      <Icon name="flame" />
      <b>{days}</b>
    </span>
  );
}

export function FloatButton({
  icon,
  label,
  onClick,
  tone = "plain",
  busy = false,
}: {
  icon: IconName;
  label: string;
  onClick: () => void;
  tone?: "plain" | "accent";
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      className="float-button glass"
      data-tone={tone}
      aria-label={label}
      title={label}
      aria-busy={busy || undefined}
      disabled={busy}
      onClick={onClick}
    >
      <Icon name={icon} />
    </button>
  );
}

export function FloatingBar({ children }: { children: React.ReactNode }) {
  return <div className="floating-bar">{children}</div>;
}

export function ReaderHero({ eyebrow, title, actions }: { eyebrow: string; title: string; actions?: React.ReactNode }) {
  return (
    <header className="reader-hero">
      <div className="reader-hero-text">
        <p className="reader-hero-eyebrow">{eyebrow}</p>
        <h1 className="reader-hero-title">{title}</h1>
      </div>
      {actions && <FloatingBar>{actions}</FloatingBar>}
    </header>
  );
}

export function Working({ children }: { children: React.ReactNode }) {
  return (
    <div className="working" role="status">
      <span className="working-dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="working-text">{children}</span>
    </div>
  );
}

export function Prose({ text }: { text: string }) {
  return (
    <div className="prose">
      {paragraphs(text).map((paragraph, index) => (
        <p key={index}>{paragraph}</p>
      ))}
    </div>
  );
}
