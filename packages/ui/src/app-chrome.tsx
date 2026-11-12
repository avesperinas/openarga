import * as React from "react";

import { CrashBoundary } from "./crash";

import {
  APP_BACKGROUNDS,
  APP_HUES,
  type AppBackground,
  type UiPreferences,
  apply,
  backgroundOf,
  backgroundStyle,
  remember,
  remembered,
  styledIcon,
} from "./appearance";
import { List, ListRow, Sheet } from "./controls";
import { Icon, type IconName } from "./icons";
import { Hint, Screen, Section } from "./screen";

export interface AppIdentity {
  id: string;
  name: string;
  icon: string;
}

const PREFERENCES = "/api/kernel/ui/preferences";

export function cameFromArga(
  app: string,
  referrer: string,
  origin: string,
  storage: Pick<Storage, "getItem" | "setItem"> | null,
): boolean {
  const key = `${app}:desde-arga`;
  try {
    if (referrer) {
      const from = new URL(referrer);
      if (from.origin === origin && !from.pathname.startsWith(`/${app}`)) {
        storage?.setItem(key, "1");
        return true;
      }
    }
    return storage?.getItem(key) === "1";
  } catch {
    return false;
  }
}

function useFromArga(app: string): boolean {
  const [from, setFrom] = React.useState(false);
  React.useEffect(() => {
    let storage: Storage | null = null;
    try {
      storage = window.sessionStorage;
    } catch {
      storage = null;
    }
    setFrom(cameFromArga(app, document.referrer, window.location.origin, storage));
  }, [app]);
  return from;
}

export function AppHome({ app, className, always = true }: { app: string; className?: string; always?: boolean }) {
  const fromArga = useFromArga(app);
  if (!fromArga && !always) return null;
  return (
    <a className={className ? `app-home ${className}` : "app-home"} href="/" aria-label="Ir al escritorio de arga">
      <Icon name="modules" />
      arga
    </a>
  );
}

export interface AppBack {
  label: string;
  onClick: () => void;
}

export function AppHeader({
  app,
  eyebrow,
  title,
  back,
}: {
  app: AppIdentity;
  eyebrow?: string;
  title?: string;
  back?: AppBack;
}) {
  const [plain, setPlain] = React.useState(false);
  const style = typeof window === "undefined" ? undefined : safeRemembered().icon_style;
  const src = plain ? app.icon : styledIcon(app.icon, style);
  return (
    <header className="app-header">
      <div className="app-brand">
        <span className="app-mark">
          <img className="app-logo" src={src} alt="" width="28" height="28" onError={() => setPlain(true)} />
          {app.name}
        </span>
        <AppHome app={app.id} />
      </div>
      {back && (
        <button type="button" className="app-back" onClick={back.onClick}>
          <Icon name="chevron-left" />
          {back.label}
        </button>
      )}
      {eyebrow && <p className="app-eyebrow">{eyebrow}</p>}
      {title && <h1 className="app-title">{title}</h1>}
    </header>
  );
}

export const SETTINGS_TAB = { id: "settings", label: "Ajustes", icon: "settings" } as const satisfies {
  id: "settings";
  label: string;
  icon: IconName;
};

export const ARGA_SETTINGS = "/#ajustes";

export function AppSettings({ app, children }: { app: AppIdentity; children?: React.ReactNode }) {
  return (
    <Screen>
      <AppHeader app={app} title="Ajustes" />
      {children}
      <AppBackgroundPicker app={app} />
      <AppAbout app={app} />
    </Screen>
  );
}

export function AppSettingsSheet({
  app,
  onClose,
  children,
}: {
  app: AppIdentity;
  onClose: () => void;
  children?: React.ReactNode;
}) {
  return (
    <Sheet title="Ajustes" onClose={onClose}>
      <div className="app-settings-sheet">
        {children}
        <AppBackgroundPicker app={app} />
        <AppAbout app={app} />
      </div>
    </Sheet>
  );
}

export function AppBackgroundPicker({ app }: { app: AppIdentity }) {
  const backdrop = useAppBackdrop();
  if (!backdrop) return null;
  return (
    <Section title="Fondo">
      <ul className="background-grid" aria-label={`Fondo de ${app.name}`}>
        {APP_BACKGROUNDS.map((option) => {
          const active = backdrop.background === option.value;
          return (
            <li key={option.value}>
              <button
                type="button"
                className="background-option"
                aria-pressed={active}
                data-active={active || undefined}
                data-background={option.value === "plain" ? "plain" : "tint"}
                style={backgroundStyle(app.id, option.value)}
                onClick={() => backdrop.ready && backdrop.choose(option.value)}
              >
                <span className="background-name">{option.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <Hint>
        Solo para {app.name}. La foto es de Hoy y Módulos; el tema y la transparencia, de todo arga,
        en sus Ajustes.
      </Hint>
    </Section>
  );
}

const versions = new Map<string, Promise<string>>();

function versionOf(id: string): Promise<string> {
  let found = versions.get(id);
  if (!found) {
    found = fetch(`/api/${id}/version`, { headers: { accept: "application/json" } })
      .then((response) => (response.ok ? (response.json() as Promise<{ version?: string }>) : {}))
      .then((body: { version?: string }) => body.version ?? "")
      .catch(() => {
        versions.delete(id);
        return "";
      });
    versions.set(id, found);
  }
  return found;
}

export function AppAbout({ app }: { app: AppIdentity }) {
  const [version, setVersion] = React.useState("");
  React.useEffect(() => {
    let live = true;
    void versionOf(app.id).then((found) => live && setVersion(found));
    return () => {
      live = false;
    };
  }, [app.id]);
  return (
    <Section title="Acerca de">
      <List>
        <ListRow title={app.name} value={version || "…"} />
        <ListRow
          title="Ajustes de arga"
          subtitle="Tema, transparencia, espacios y Claude"
          accessory="chevron-right"
          onClick={() => window.location.assign(ARGA_SETTINGS)}
        />
      </List>
    </Section>
  );
}

export interface AppBackdropValue {
  background: AppBackground;
  ready: boolean;
  choose: (background: AppBackground) => void;
}

const BackdropContext = React.createContext<AppBackdropValue | null>(null);
export const useAppBackdrop = () => React.useContext(BackdropContext);

function safeRemembered(): Partial<UiPreferences> {
  return typeof window === "undefined" ? {} : remembered();
}

export function AppBackdrop({
  app,
  className,
  colored = false,
  children,
}: {
  app: string;
  className?: string;
  colored?: boolean;
  children: React.ReactNode;
}) {
  const [preferences, setPreferences] = React.useState<Partial<UiPreferences>>(() =>
    safeRemembered(),
  );
  const [ready, setReady] = React.useState(false);
  const latest = React.useRef(preferences);

  React.useEffect(() => {
    void fetch(PREFERENCES, { headers: { accept: "application/json" } })
      .then((response) => (response.ok ? (response.json() as Promise<UiPreferences>) : null))
      .catch(() => null)
      .then((stored) => {
        if (!stored) return;
        apply(stored);
        remember(stored);
        latest.current = stored;
        setPreferences(stored);
        setReady(true);
      });
  }, []);

  const choose = React.useCallback(
    (background: AppBackground) => {
      const current = latest.current as UiPreferences;
      const next: UiPreferences = {
        ...current,
        app_backgrounds: { ...(current.app_backgrounds ?? {}), [app]: background },
      };
      latest.current = next;
      setPreferences(next);
      remember(next);
      void fetch(PREFERENCES, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(next),
      });
    },
    [app],
  );

  const background = backgroundOf(app, preferences);

  return (
    <BackdropContext.Provider value={{ background, ready, choose }}>
      <div
        className={className ? `app-desktop ${className}` : "app-desktop"}
        data-background={background === "plain" ? "plain" : "tint"}
        data-kind={colored && APP_HUES[app] ? `hue-${APP_HUES[app]}` : undefined}
        style={backgroundStyle(app, background)}
      >
        <CrashBoundary home={`/${app}/`}>{children}</CrashBoundary>
      </div>
    </BackdropContext.Provider>
  );
}

export function applyRemembered(): void {
  const saved = safeRemembered();
  if (saved.theme && typeof saved.glass_opacity === "number") {
    apply({
      theme: saved.theme,
      glass_opacity: saved.glass_opacity,
      wallpaper: saved.wallpaper ?? "",
    });
  }
}
