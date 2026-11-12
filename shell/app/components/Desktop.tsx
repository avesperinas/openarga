"use client";

import { ConfirmDelete, Hint, Icon, Section, WallpaperLayer } from "@openarga/ui";
import * as React from "react";

import type { ModuleSummary } from "../lib/kernel";
import { type UiPreferences, apply, remember } from "../lib/preferences";
import { request } from "../lib/session";
import {
  WALLPAPERS,
  type Wallpaper,
  shrink,
  wallpaperOf,
  wallpaperStyle,
} from "../lib/wallpaper";
import { TabBar } from "./TabBar";

const SAVE_DEBOUNCE = 400;

const Context = React.createContext<{
  current: Wallpaper;
  preferences: UiPreferences;
  choose: (id: string) => void;
  change: (next: Partial<UiPreferences>) => void;
  mine: Wallpaper[];
  upload: (file: File) => Promise<void>;
  forget: (id: string) => Promise<void>;
  frame: (id: string, focus: { x: number; y: number }) => void;
  failed: string | null;
  uploading: boolean;
  editing: boolean;
  setEditing: (editing: boolean) => void;
} | null>(null);

export const useDesktop = () => React.useContext(Context);

export function Desktop({
  initial,
  modules,
  wallpapers,
  children,
}: {
  initial: UiPreferences;
  modules: ModuleSummary[];
  wallpapers: Wallpaper[];
  children: React.ReactNode;
}) {
  const [preferences, setPreferences] = React.useState(initial);
  const [mine, setMine] = React.useState(wallpapers);
  const [failed, setFailed] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const latest = React.useRef(initial);
  const timer = React.useRef<ReturnType<typeof setTimeout>>(undefined);
  const current = wallpaperOf(preferences.wallpaper, mine);

  React.useEffect(() => {
    latest.current = initial;
    apply(initial);
    remember(initial);
  }, [initial]);

  const change = React.useCallback((next: Partial<UiPreferences>) => {
    const merged = { ...latest.current, ...next };
    latest.current = merged;
    setPreferences(merged);
    apply(merged);
    remember(merged);

    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void request("/api/kernel/ui/preferences", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(latest.current),
      });
    }, SAVE_DEBOUNCE);
  }, []);

  const choose = React.useCallback((next: string) => change({ wallpaper: next }), [change]);

  const upload = React.useCallback(
    async (file: File) => {
      setFailed(null);
      setUploading(true);
      try {
        const body = new FormData();
        const reduced = await shrink(file);
        body.append("file", reduced, reduced === file ? file.name : "fondo.jpg");
        const response = await request("/api/kernel/ui/wallpapers", { method: "POST", body });

        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          setFailed(
            typeof detail?.detail === "string"
              ? `No se pudo usar esta imagen: ${detail.detail}.`
              : "No se pudo subir la imagen. Inténtalo otra vez.",
          );
          return;
        }

        const saved = (await response.json()) as Wallpaper;
        setMine((previous) => [saved, ...previous]);
        change({ wallpaper: saved.id });
      } catch {
        setFailed("No llegó a subirse: parece que no hay conexión. Inténtalo otra vez.");
      } finally {
        setUploading(false);
      }
    },
    [change],
  );

  const framing = React.useRef<ReturnType<typeof setTimeout>>(undefined);
  const frame = React.useCallback((id: string, focus: { x: number; y: number }) => {
    setMine((previous) =>
      previous.map((entry) => (entry.id === id ? { ...entry, focus } : entry)),
    );
    clearTimeout(framing.current);
    framing.current = setTimeout(() => {
      void request(`/api/kernel/ui/wallpapers/${id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ focus }),
      }).catch(() => undefined);
    }, SAVE_DEBOUNCE);
  }, []);

  const forget = React.useCallback(
    async (id: string) => {
      await request(`/api/kernel/ui/wallpapers/${id}`, { method: "DELETE" });
      setMine((previous) => previous.filter((entry) => entry.id !== id));
      if (latest.current.wallpaper === id) change({ wallpaper: WALLPAPERS[0]!.id });
    },
    [change],
  );

  return (
    <Context.Provider
      value={{
        current,
        preferences,
        choose,
        change,
        mine,
        upload,
        forget,
        frame,
        failed,
        uploading,
        editing,
        setEditing,
      }}
    >
      <div
        className="desktop"
        data-wallpaper="desktop"
        data-editing={editing || undefined}
        style={wallpaperStyle(current)}
      >
        <WallpaperLayer wallpaper={current} />
        {children}
        <TabBar modules={modules} />
      </div>
    </Context.Provider>
  );
}

export function WallpaperSheet() {
  const desktop = useDesktop();
  const input = React.useRef<HTMLInputElement>(null);
  const [forgetting, setForgetting] = React.useState<Wallpaper | null>(null);
  if (!desktop) return null;

  const entries = [...desktop.mine, ...WALLPAPERS];
  const own = desktop.mine.some((entry) => entry.id === desktop.current.id);

  return (
    <Section title="Fondo">

      <ul className="wallpaper-grid">
        <li>
          <button
            type="button"
            className="wallpaper-option wallpaper-upload"
            disabled={desktop.uploading}
            onClick={() => input.current?.click()}
          >
            <Icon name={desktop.uploading ? "image" : "plus"} />
            <span className="wallpaper-upload-label">
              {desktop.uploading ? "Subiendo…" : "Subir la mía"}
            </span>
          </button>
          <input
            ref={input}
            type="file"
            className="wallpaper-input"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void desktop.upload(file);
            }}
          />
        </li>

        {entries.map((entry) => {
          const active = entry.id === desktop.current.id;
          const own = desktop.mine.some((candidate) => candidate.id === entry.id);
          return (
            <li key={entry.id} className="wallpaper-slot">
              <button
                type="button"
                className="wallpaper-option"
                aria-pressed={active}
                data-active={active || undefined}
                style={
                  {
                    "--wallpaper-swatch": `url(${entry.thumb ?? entry.image})`,
                  } as React.CSSProperties
                }
                onClick={() => desktop.choose(entry.id)}
              >
                <span className="wallpaper-name">{entry.name}</span>
              </button>
              {own && (
                <button
                  type="button"
                  className="wallpaper-forget"
                  aria-label={`Borrar el fondo ${entry.name}`}
                  onClick={() => setForgetting(entry)}
                >
                  <Icon name="close" />
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {forgetting && (
        <ConfirmDelete
          title="¿Borrar este fondo?"
          subject={forgetting.name}
          consequence="La imagen que subiste se borra. Si estaba puesta, vuelve el fondo por defecto. No se puede deshacer."
          action="Borrar fondo"
          onCancel={() => setForgetting(null)}
          onConfirm={() => desktop.forget(forgetting.id).then(() => setForgetting(null))}
        />
      )}

      {desktop.failed && (
        <p className="wallpaper-rejected" role="alert">
          {desktop.failed}
        </p>
      )}

      {own && <Framing wallpaper={desktop.current} onFrame={desktop.frame} />}

      <Hint>
        El sistema oscurece o aclara la foto lo justo para que lo que va encima se lea: en esta,
        hasta un {Math.round(desktop.current.scrim.light * 100)}% en claro y un{" "}
        {Math.round(desktop.current.scrim.dark * 100)}% en oscuro, y menos en el centro.
      </Hint>
      <Hint>Este es el del escritorio. Cada app puede llevar el suyo: se elige en sus Ajustes.</Hint>
    </Section>
  );
}

function Framing({
  wallpaper,
  onFrame,
}: {
  wallpaper: Wallpaper;
  onFrame: (id: string, focus: { x: number; y: number }) => void;
}) {
  const focus = wallpaper.focus ?? { x: 0.5, y: 0.5 };
  const clamp = (value: number) => Math.min(1, Math.max(0, Math.round(value * 100) / 100));
  const place = (x: number, y: number) => onFrame(wallpaper.id, { x: clamp(x), y: clamp(y) });

  const onPointer = (event: React.PointerEvent<HTMLButtonElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    place((event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
  };

  const onKey = (event: React.KeyboardEvent) => {
    const step = 0.05;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    place(focus.x + move[0], focus.y + move[1]);
  };

  return (
    <div className="wallpaper-framing">
      <h4 className="sheet-group">Encuadre</h4>
      <button
        type="button"
        className="wallpaper-frame"
        aria-label={`Punto que queda a la vista: ${Math.round(focus.x * 100)}% desde la izquierda y ${Math.round(focus.y * 100)}% desde arriba. Toca o usa las flechas para moverlo.`}
        onPointerDown={onPointer}
        onKeyDown={onKey}
      >
        <img src={wallpaper.image} alt="" draggable={false} />
        <span
          className="wallpaper-focus"
          style={
            {
              "--focus-x": `${focus.x * 100}%`,
              "--focus-y": `${focus.y * 100}%`,
            } as React.CSSProperties
          }
        />
      </button>
      <Hint>Toca lo que quieres ver cuando la pantalla recorta la foto.</Hint>
    </div>
  );
}
