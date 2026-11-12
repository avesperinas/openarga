import * as React from "react";

import { Button } from "./controls";
import { Icon, IconBadge, type IconName } from "./icons";

export interface CoverProps {
  title: string;
  subtitle?: string;
  src?: string | null;
  size?: "small" | "regular" | "large" | "hero";
}

export function Cover({ title, subtitle, src, size = "regular" }: CoverProps) {
  return (
    <span className="cover" data-size={size}>
      {src ? (
        <img src={src} alt={`Portada de ${title}`} loading="lazy" decoding="async" />
      ) : (
        <span className="cover-blank" aria-label={title}>
          <span className="cover-title">{title}</span>
          {subtitle && <span className="cover-subtitle">{subtitle}</span>}
        </span>
      )}
    </span>
  );
}

export interface CoverWallItem {
  id: string;
  title: string;
  subtitle?: string;
  src?: string | null;
  note?: string;
  muted?: boolean;
}

export function CoverWall({ items, onOpen, label }: { items: CoverWallItem[]; onOpen: (id: string) => void; label?: string }) {
  return (
    <ul className="cover-wall" aria-label={label}>
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            className="cover-wall-item"
            data-muted={item.muted || undefined}
            aria-label={item.title}
            onClick={() => onOpen(item.id)}
          >
            <Cover title={item.title} subtitle={item.subtitle} src={item.src} />
            {item.note && <span className="cover-wall-note">{item.note}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}

export interface MediaCardProps {
  media: React.ReactNode;
  title: string;
  lines?: React.ReactNode[];
  onOpen: () => void;
  action?: { label: string; icon?: IconName; onClick: () => void; disabled?: boolean };
}

export function MediaCard({ media, title, lines = [], onOpen, action }: MediaCardProps) {
  return (
    <div className="surface media-card">
      <button type="button" className="media-card-open" onClick={onOpen}>
        {media}
        <span className="media-card-text">
          <span className="media-card-title">{title}</span>
          {lines.map((line, index) => (
            <span key={index} className="media-card-line" data-first={index === 0 || undefined}>
              {line}
            </span>
          ))}
        </span>
      </button>
      {action && (
        <Button variant="tinted" icon={action.icon} disabled={action.disabled} onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

export function MediaHero({ media, children }: { media: React.ReactNode; children?: React.ReactNode }) {
  return (
    <section className="media-hero">
      {media}
      {children && <div className="media-hero-text">{children}</div>}
    </section>
  );
}

export type TileHue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export interface TileProps {
  title: string;
  hue: TileHue;
  figure?: React.ReactNode;
  caption?: string;
  glyph?: React.ReactNode;
  detail?: string;
  tags?: string[];
  href?: string;
  onOpen?: () => void;
  muted?: boolean;
}

export function Tile({ title, hue, figure, caption, glyph, detail, tags = [], href, onOpen, muted = false }: TileProps) {
  const body = (
    <>
      <span className="tile-face" data-hue={hue}>
        {glyph && (
          <span className="tile-glyph" aria-hidden="true">
            {glyph}
          </span>
        )}
        {figure !== undefined && (
          <span className="tile-figure">
            {figure}
            {caption && <span className="tile-caption">{caption}</span>}
          </span>
        )}
      </span>
      <span className="tile-text">
        <span className="tile-title">{title}</span>
        {detail && <span className="tile-detail">{detail}</span>}
        {tags.length > 0 && (
          <span className="tile-tags">
            {tags.map((tag) => (
              <span key={tag} className="tile-tag">
                {tag}
              </span>
            ))}
          </span>
        )}
      </span>
    </>
  );
  if (href) {
    return (
      <a
        className="surface tile"
        data-muted={muted || undefined}
        href={href}
        onClick={(event) => {
          if (!onOpen || event.metaKey || event.ctrlKey) return;
          event.preventDefault();
          onOpen();
        }}
      >
        {body}
      </a>
    );
  }
  return (
    <button type="button" className="surface tile" data-muted={muted || undefined} onClick={onOpen}>
      {body}
    </button>
  );
}

export function Tiles({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <ul className="tiles" aria-label={label}>
      {React.Children.map(children, (child) => (child ? <li>{child}</li> : null))}
    </ul>
  );
}

export function Banner({ hue, glyph, children }: { hue: TileHue; glyph?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="surface banner" data-hue={hue}>
      {glyph && (
        <span className="banner-glyph" aria-hidden="true">
          {glyph}
        </span>
      )}
      {children}
    </div>
  );
}

export interface PhotoProps {
  src?: string | null;
  alt?: string;
  hue: TileHue;
  icon: IconName;
  shape?: "card" | "hero" | "banner";
  badge?: string;
  badgeTone?: "warning";
  action?: { label: string; onClick: () => void };
  loading?: "lazy" | "eager";
}

export function Photo({ src, alt = "", hue, icon, shape = "card", badge, badgeTone, action, loading = "lazy" }: PhotoProps) {
  const inside = (
    <>
      {src ? <img src={src} alt={alt} loading={loading} draggable={false} /> : <IconBadge name={icon} hue={hue} />}
      {badge && (
        <span className="photo-badge" data-tone={badgeTone}>
          {badge}
        </span>
      )}
      {action && <span className="photo-action">{action.label}</span>}
    </>
  );
  if (action) {
    return (
      <button type="button" className="photo" data-shape={shape} data-hue={hue} onClick={action.onClick}>
        {inside}
      </button>
    );
  }
  return (
    <span className="photo" data-shape={shape} data-hue={hue}>
      {inside}
    </span>
  );
}

export interface PhotoTileProps extends Pick<PhotoProps, "src" | "hue" | "icon" | "badge" | "badgeTone"> {
  title: string;
  shared?: boolean;
  muted?: boolean;
  detail?: string;
  href?: string;
  onOpen?: () => void;
}

export function PhotoTile({ title, detail, href, onOpen, shared = false, muted = false, ...photo }: PhotoTileProps) {
  const body = (
    <>
      <Photo {...photo} />
      <span className="tile-text">
        <span className="tile-title">
          {title}
          {shared && <Icon name="people" label="Compartido" />}
        </span>
        {detail && <span className="tile-detail">{detail}</span>}
      </span>
    </>
  );
  if (href) {
    return (
      <a
        className="surface tile"
        data-muted={muted || undefined}
        href={href}
        onClick={(event) => {
          if (!onOpen || event.metaKey || event.ctrlKey) return;
          event.preventDefault();
          onOpen();
        }}
      >
        {body}
      </a>
    );
  }
  return (
    <button type="button" className="surface tile" data-muted={muted || undefined} onClick={onOpen}>
      {body}
    </button>
  );
}
