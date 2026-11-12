import type { Author } from "./api";

const day = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });
const dayYear = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric" });
const clock = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });

export function ago(iso: string, now = new Date()): string {
  const then = new Date(iso);
  const minutes = Math.floor((now.getTime() - then.getTime()) / 60_000);
  if (minutes < 1) return "ahora";
  if (minutes < 60) return `hace ${minutes} min`;
  if (minutes < 60 * 24 && then.getDate() === now.getDate()) return `hoy, ${clock.format(then)}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (then.toDateString() === yesterday.toDateString()) return `ayer, ${clock.format(then)}`;
  return then.getFullYear() === now.getFullYear() ? day.format(then) : dayYear.format(then);
}

export function who(author: Author, app?: string | null): string {
  if (author === "import" && app) return app;
  return author === "tool" ? "Claude" : author === "import" ? "La importación" : "Tú";
}
