import { addDays, dayKey } from "@openarga/ui";

import type { EventDraft, Occurrence } from "./api";
import { t } from "./lang";

export interface Form {
  title: string;
  calendarId: string;
  allDay: boolean;
  startDay: string;
  startTime: string;
  endDay: string;
  endTime: string;
  location: string;
  url: string;
  notes: string;
  rrule: string | null;
}

const pad = (n: number) => String(n).padStart(2, "0");
export const clockOf = (date: Date) => `${pad(date.getHours())}:${pad(date.getMinutes())}`;

function at(day: string, time: string): Date {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const [h, mi] = (time || "00:00").split(":").map(Number) as [number, number];
  return new Date(y, m - 1, d, h, mi);
}

export function blankForm(start: Date, end: Date, calendarId: string, allDay = false): Form {
  const lastDay = allDay ? addDays(dayKey(end), -1) : dayKey(end);
  return {
    title: "",
    calendarId,
    allDay,
    startDay: dayKey(start),
    startTime: clockOf(start),
    endDay: allDay ? (lastDay < dayKey(start) ? dayKey(start) : lastDay) : lastDay,
    endTime: clockOf(end),
    location: "",
    url: "",
    notes: "",
    rrule: null,
  };
}

export function formOf(occurrence: Occurrence, rrule: string | null): Form {
  if (occurrence.all_day) {
    return {
      ...blankForm(new Date(), new Date(), occurrence.calendar_id, true),
      title: occurrence.title,
      startDay: occurrence.start,
      endDay: addDays(occurrence.end, -1),
      location: occurrence.location ?? "",
      url: occurrence.url ?? "",
      notes: occurrence.notes ?? "",
      rrule,
    };
  }
  const start = new Date(occurrence.start);
  const end = new Date(occurrence.end);
  return {
    title: occurrence.title,
    calendarId: occurrence.calendar_id,
    allDay: false,
    startDay: dayKey(start),
    startTime: clockOf(start),
    endDay: dayKey(end),
    endTime: clockOf(end),
    location: occurrence.location ?? "",
    url: occurrence.url ?? "",
    notes: occurrence.notes ?? "",
    rrule,
  };
}

export function problemOf(form: Form): string | null {
  if (!form.title.trim()) return t("form.no_title");
  if (form.allDay) {
    if (form.endDay < form.startDay) return t("form.last_before_first");
    return null;
  }
  if (at(form.endDay, form.endTime) < at(form.startDay, form.startTime)) return t("form.end_before_start");
  if (form.url.trim() && !/^https?:\/\//.test(form.url.trim())) return t("form.bad_link");
  return null;
}

export function draftOf(form: Form, tz: string): EventDraft {
  const clean = (text: string) => text.trim() || null;
  const timing = form.allDay
    ? { start: form.startDay, end: addDays(form.endDay, 1) }
    : {
        start: at(form.startDay, form.startTime).toISOString(),
        end: at(form.endDay, form.endTime).toISOString(),
      };
  return {
    calendar_id: form.calendarId,
    title: form.title.trim(),
    all_day: form.allDay,
    ...timing,
    tz,
    location: clean(form.location),
    url: clean(form.url),
    notes: clean(form.notes),
    rrule: form.rrule,
  };
}

export function changesOf(before: Form, after: Form, tz: string): EventDraft {
  const a = draftOf(before, tz);
  const b = draftOf(after, tz);
  const out: EventDraft = {};
  const keys = Object.keys(b) as (keyof EventDraft)[];
  for (const key of keys) {
    if (key === "tz") continue;
    if (JSON.stringify(a[key]) !== JSON.stringify(b[key])) (out as Record<string, unknown>)[key] = b[key];
  }
  if ("start" in out || "end" in out || "all_day" in out) {
    out.start = b.start;
    out.end = b.end;
    out.all_day = b.all_day;
  }
  return out;
}

export function moveStart(form: Form, startDay: string, startTime: string): Form {
  if (form.allDay) {
    const span = Math.round((at(form.endDay, "12:00").getTime() - at(form.startDay, "12:00").getTime()) / 86_400_000);
    return { ...form, startDay, endDay: addDays(startDay, span) };
  }
  const duration = at(form.endDay, form.endTime).getTime() - at(form.startDay, form.startTime).getTime();
  const end = new Date(at(startDay, startTime).getTime() + duration);
  return { ...form, startDay, startTime, endDay: dayKey(end), endTime: clockOf(end) };
}
