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
    { app: "planner", app_name: "Planner", kind: "renewal", label: "Renewal", enabled: false },
  ],
  quiet_from: "23:00:00",
  quiet_to: "08:00:00",
};

describe("notifications in Settings", () => {
  it("each app with its kinds, together", () => {
    expect(groupByApp(settings).map(([app, name, kinds]) => [app, name, kinds.map((one) => one.kind)])).toEqual([
      ["planner", "Planner", ["reminder", "renewal"]],
      ["study", "Study", ["assessment"]],
    ]);
  });

  it("the device is named after what it is", () => {
    expect(deviceName("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)")).toBe("iPhone");
    expect(deviceName("Mozilla/5.0 (X11; Linux x86_64)")).toBe("Linux");
    expect(deviceName("something odd")).toBe("This device");
  });

  it("the public key travels as base64url and subscribes with its bytes", () => {
    expect([...keyBytes("AQID_-8")]).toEqual([1, 2, 3, 255, 239]);
  });

  it("a device shows its last error if it is later than the last notification that arrived", () => {
    const device = { id: "1", name: "iPhone", created_at: "2026-10-01T08:00:00Z" };
    expect(deviceDetail({ ...device, last_sent: null })).toBe("no notifications yet");
    const failed = deviceDetail({
      ...device,
      last_sent: "2026-10-20T08:00:00Z",
      last_error: "403 BadJwtToken",
      last_error_at: "2026-10-21T08:00:00Z",
    });
    expect(failed).toMatch(/^last notification .* · failed .*: 403 BadJwtToken$/);
    const fixed = deviceDetail({
      ...device,
      last_sent: "2026-10-22T08:00:00Z",
      last_error: "403 BadJwtToken",
      last_error_at: "2026-10-21T08:00:00Z",
    });
    expect(fixed).not.toContain("failed");
  });

  it("the test says whom it did not reach and why", () => {
    expect(testSaid({ sent: 1, forgotten: 0, failed: [] })).toBe("A test notification was sent.");
    expect(testSaid({ sent: 0, forgotten: 0, failed: [{ device: "iPhone", reason: "403 BadJwtToken" }] })).toBe(
      "It did not reach any device. iPhone: 403 BadJwtToken.",
    );
  });

  it("the latest says what happened to each notification", () => {
    const base = { app: "planner", title: "Vence el seguro", due_at: "2026-10-20T07:00:00Z", attempts: 0 };
    expect(recentDetail({ ...base, sent_at: "2026-10-20T07:00:10Z", outcome: "sent to 1 of 1" })).toMatch(
      / · sent to 1 of 1$/,
    );
    expect(recentDetail({ ...base, sent_at: null, outcome: "sent to 0 of 1; iPhone: no answer" })).toMatch(
      / · retrying: sent to 0 of 1; iPhone: no answer$/,
    );
    expect(recentDetail({ ...base, sent_at: null, outcome: null })).toMatch(/ · waiting$/);
  });
});
