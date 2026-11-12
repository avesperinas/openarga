import { request } from "./session";

export interface NotificationKind {
  app: string;
  app_name: string;
  kind: string;
  label: string;
  enabled: boolean;
}

export interface Device {
  id: string;
  name: string;
  created_at: string;
  last_sent: string | null;
  last_error?: string | null;
  last_error_at?: string | null;
}

export interface RecentNotification {
  app: string;
  title: string;
  due_at: string;
  sent_at: string | null;
  outcome: string | null;
  attempts: number;
}

export interface NotificationSettings {
  configured: boolean;
  public_key: string | null;
  devices: Device[];
  kinds: NotificationKind[];
  quiet_from: string | null;
  quiet_to: string | null;
  recent?: RecentNotification[];
  late?: number;
}

export interface TestResult {
  sent: number;
  forgotten: number;
  failed?: { device: string; reason: string }[];
}

const BASE = "/api/kernel/notifications";

export class NotificationError extends Error {}

async function call<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const response = await request(`${BASE}${path}`, {
    ...rest,
    headers: json === undefined ? undefined : { "content-type": "application/json" },
    body: json === undefined ? undefined : JSON.stringify(json),
  });
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    throw new NotificationError(detail ?? "No se ha podido hacer. Prueba otra vez en un momento.");
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const readNotifications = () => call<NotificationSettings>("");
export const removeDevice = (id: string) => call<void>(`/devices/${id}`, { method: "DELETE" });
export const setKind = (app: string, kind: string, enabled: boolean) =>
  call<void>("/prefs", { method: "PUT", json: { app, kind, enabled } });
export const setQuiet = (from: string | null, to: string | null) =>
  call<void>("/quiet", { method: "PUT", json: { quiet_from: from, quiet_to: to } });
export const sendTest = () => call<TestResult>("/test", { method: "POST" });

const when = (iso: string) =>
  new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function deviceDetail(device: Device): string {
  const sent = device.last_sent ? `último aviso ${when(device.last_sent)}` : "aún sin avisos";
  const failedLater =
    device.last_error && device.last_error_at && (!device.last_sent || device.last_error_at > device.last_sent);
  return failedLater ? `${sent} · falló ${when(device.last_error_at as string)}: ${device.last_error}` : sent;
}

export function testSaid(result: TestResult): string {
  const failed = result.failed ?? [];
  if (result.sent && !failed.length) return "Enviado un aviso de prueba.";
  const head = result.sent ? `Enviado a ${result.sent}.` : "No ha llegado a ningún dispositivo.";
  return [head, ...failed.map((one) => `${one.device}: ${one.reason}.`)].join(" ");
}

export function recentDetail(one: RecentNotification): string {
  const at = when(one.sent_at ?? one.due_at);
  if (!one.sent_at) return one.outcome ? `${at} · reintentando: ${one.outcome}` : `${at} · esperando`;
  return `${at} · ${one.outcome ?? "enviado"}`;
}

export type Support = "none" | "ready" | "install";

export function support(): Support {
  if (typeof window === "undefined") return "none";
  const standalone =
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  const apple = /iPhone|iPad|iPod/.test(navigator.userAgent);
  if (apple && !standalone) return "install";
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return "none";
  }
  return "ready";
}

export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(base64url.length / 4) * 4, "=");
  const raw = atob(padded);
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) out[index] = raw.charCodeAt(index);
  return out;
}

export function deviceName(agent: string = typeof navigator === "undefined" ? "" : navigator.userAgent): string {
  if (/iPhone/.test(agent)) return "iPhone";
  if (/iPad/.test(agent)) return "iPad";
  if (/Android/.test(agent)) return "Android";
  if (/Macintosh/.test(agent)) return "Mac";
  if (/Windows/.test(agent)) return "Windows";
  if (/Linux/.test(agent)) return "Linux";
  return "Este dispositivo";
}

export async function enableHere(publicKey: string): Promise<Device> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new NotificationError("Sin permiso no hay avisos. Se cambia en los ajustes del navegador.");
  }
  const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) }));
  const body = subscription.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
  return call<Device>("/devices", {
    method: "POST",
    json: { endpoint: body.endpoint, keys: body.keys, name: deviceName() },
  });
}
