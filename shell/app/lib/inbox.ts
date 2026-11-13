import { dates, regional } from "@openarga/ui";

import { request } from "./session";

export interface Notice {
  id: string;
  app: string;
  app_name: string;
  title: string;
  body: string | null;
  href: string;
  sent_at: string;
  read: boolean;
}

export interface Day {
  key: string;
  label: string;
  notices: Notice[];
}

const BASE = "/api/kernel/notifications/inbox";

export async function readInbox(): Promise<Notice[]> {
  const response = await request(BASE, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`la bandeja contestó ${response.status}`);
  return (await response.json()) as Notice[];
}

export function markRead(id: string): void {
  void fetch(`${BASE}/${encodeURIComponent(id)}/read`, {
    method: "POST",
    credentials: "same-origin",
    keepalive: true,
  }).catch(() => undefined);
}

const dayKey = (date: Date) => `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;

export function byDay(notices: Notice[], now: Date = new Date()): Day[] {
  const today = dayKey(now);
  const yesterday = dayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
  const long = dates({ weekday: "long", day: "numeric", month: "long" });
  const days: Day[] = [];
  for (const notice of [...notices].sort((a, b) => b.sent_at.localeCompare(a.sent_at))) {
    const at = new Date(notice.sent_at);
    const key = dayKey(at);
    let day = days.at(-1);
    if (!day || day.key !== key) {
      const label = key === today ? "Hoy" : key === yesterday ? "Ayer" : long.format(at);
      day = { key, label: label.charAt(0).toLocaleUpperCase(regional().locale) + label.slice(1), notices: [] };
      days.push(day);
    }
    day.notices.push(notice);
  }
  return days;
}

export const timeOf = (iso: string) =>
  dates({ hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
