import { describe, expect, it } from "vitest";

import {
  deviceDetail,
  deviceName,
  keyBytes,
  type NotificationSettings,
  recentDetail,
  testSaid,
} from "../lib/notifications";
import { groupByApp } from "./Notifications";

const settings: NotificationSettings = {
  configured: true,
  public_key: "BAAB",
  devices: [],
  kinds: [
    { app: "planner", app_name: "Planner", kind: "reminder", label: "Recordatorio", enabled: true },
    { app: "study", app_name: "Study", kind: "assessment", label: "Evaluable", enabled: false },
    { app: "planner", app_name: "Planner", kind: "renewal", label: "Renovación", enabled: false },
  ],
  quiet_from: "23:00:00",
  quiet_to: "08:00:00",
};

describe("los avisos en Ajustes", () => {
  it("cada app con sus tipos, juntos", () => {
    expect(groupByApp(settings).map(([app, name, kinds]) => [app, name, kinds.map((one) => one.kind)])).toEqual([
      ["planner", "Planner", ["reminder", "renewal"]],
      ["study", "Study", ["assessment"]],
    ]);
  });

  it("el dispositivo se llama por lo que es", () => {
    expect(deviceName("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)")).toBe("iPhone");
    expect(deviceName("Mozilla/5.0 (X11; Linux x86_64)")).toBe("Linux");
    expect(deviceName("algo raro")).toBe("Este dispositivo");
  });

  it("la clave pública viaja en base64url y se suscribe con sus bytes", () => {
    expect([...keyBytes("AQID_-8")]).toEqual([1, 2, 3, 255, 239]);
  });

  it("un dispositivo dice su último error si es posterior al último aviso que llegó", () => {
    const device = { id: "1", name: "iPhone", created_at: "2026-10-01T08:00:00Z" };
    expect(deviceDetail({ ...device, last_sent: null })).toBe("aún sin avisos");
    const failed = deviceDetail({
      ...device,
      last_sent: "2026-10-20T08:00:00Z",
      last_error: "403 BadJwtToken",
      last_error_at: "2026-10-21T08:00:00Z",
    });
    expect(failed).toMatch(/^último aviso .* · falló .*: 403 BadJwtToken$/);
    const fixed = deviceDetail({
      ...device,
      last_sent: "2026-10-22T08:00:00Z",
      last_error: "403 BadJwtToken",
      last_error_at: "2026-10-21T08:00:00Z",
    });
    expect(fixed).not.toContain("falló");
  });

  it("la prueba dice a quién no llegó y por qué", () => {
    expect(testSaid({ sent: 1, forgotten: 0, failed: [] })).toBe("Enviado un aviso de prueba.");
    expect(testSaid({ sent: 0, forgotten: 0, failed: [{ device: "iPhone", reason: "403 BadJwtToken" }] })).toBe(
      "No ha llegado a ningún dispositivo. iPhone: 403 BadJwtToken.",
    );
  });

  it("lo último dice qué pasó con cada aviso", () => {
    const base = { app: "planner", title: "Vence el seguro", due_at: "2026-10-20T07:00:00Z", attempts: 0 };
    expect(recentDetail({ ...base, sent_at: "2026-10-20T07:00:10Z", outcome: "enviado a 1 de 1" })).toMatch(
      / · enviado a 1 de 1$/,
    );
    expect(recentDetail({ ...base, sent_at: null, outcome: "enviado a 0 de 1; iPhone: sin respuesta" })).toMatch(
      / · reintentando: enviado a 0 de 1; iPhone: sin respuesta$/,
    );
    expect(recentDetail({ ...base, sent_at: null, outcome: null })).toMatch(/ · esperando$/);
  });
});
