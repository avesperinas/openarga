import { intlLocale } from "@openarga/ui";
import { headers } from "next/headers";

import { Dashboard } from "./components/Dashboard";
import { HomeProvider } from "./components/Home";
import { Desktop } from "./components/Desktop";
import { Inbox } from "./components/Inbox";
import { TodayDate } from "./components/TodayDate";
import { PlatformVersion } from "./components/Version";
import {
  type Device,
  type Envelope,
  launchable,
  readCatalogue,
  readDesktops,
  readModules,
  readPreferences,
  readWallpapers,
  readArea,
  readWidget,
  envelopeKey,
  widgetUrl,
} from "./lib/kernel";
import { appIcons } from "./lib/app-icons";
import { type PersonPreferences, fromHeaders } from "./lib/regional";
import { type AreaKey, type Contributor, placedAreas, shownAreas } from "./lib/panels";

export const dynamic = "force-dynamic";

const WIDGET_LIMIT_MS = 10_000;

const PANEL_LIMIT_MS = 6_000;

function today(person: PersonPreferences): string {
  return new Intl.DateTimeFormat(intlLocale(person.locale, person.country), {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: person.timezone,
  }).format(new Date());
}

async function guessDevice(): Promise<Device> {
  const agent = (await headers()).get("user-agent") ?? "";
  return /Mobi/i.test(agent) ? "mobile" : "desktop";
}

export default async function Today() {
  const person = fromHeaders(await headers());
  const [desks, device, catalogue, preferences, modules, wallpapers] = await Promise.all([
    readDesktops(),
    guessDevice(),
    readCatalogue(),
    readPreferences(),
    readModules(),
    readWallpapers().catch(() => []),
  ]);

  const endpoints = new Map(
    catalogue.map((entry) => [`${entry.source}/${entry.id}`, entry.endpoint]),
  );
  const needed = new Map<string, string>();
  for (const item of desks[device].pages.flatMap((page) => page.items)) {
    const endpoint = endpoints.get(`${item.source}/${item.widget}`);
    if (endpoint) needed.set(envelopeKey(item.source, item.widget, item.option), widgetUrl(endpoint, item.option));
  }

  const pending: Record<string, Promise<Envelope | null>> = {};
  for (const [key, url] of needed) {
    pending[key] = readWidget(url, WIDGET_LIMIT_MS).catch(() => null);
  }

  const apps = launchable(modules);
  const panels: Partial<Record<AreaKey, Promise<Contributor[]>>> = {};
  const migrating = !preferences.home_panels?.placed?.includes(device);
  const wanted = new Set([...placedAreas(desks[device].pages), ...(migrating ? shownAreas(preferences.home_panels) : [])]);
  for (const area of wanted) {
    panels[area] = readArea(area, apps, PANEL_LIMIT_MS).catch(() => []);
  }

  return (
    <Desktop initial={preferences} person={person} modules={launchable(modules)} wallpapers={wallpapers}>
      <main className="page" aria-label="Hoy">
        <header className="desktop-brand">
          <span className="desktop-mark">
            <img className="desktop-logo" src="/icon.svg" alt="" width={28} height={28} />
            arga
          </span>
          <div className="desktop-actions">
            <TodayDate initial={today(person)} />
            <Inbox />
          </div>
        </header>

        <HomeProvider>
          <Dashboard
            desks={desks}
            device={device}
            catalogue={catalogue}
            pending={pending}
            panels={panels}
            icons={appIcons(modules, preferences.icon_style)}
          />
        </HomeProvider>

        <PlatformVersion />
      </main>
    </Desktop>
  );
}
