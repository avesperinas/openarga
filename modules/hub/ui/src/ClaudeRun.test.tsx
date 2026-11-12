import type { ClaudeRunApp } from "./api";
import { authorizeClaudeRun } from "./api";
import { grantLine } from "./ClaudeRun";

const app = (granted: ClaudeRunApp["granted"]): ClaudeRunApp => ({ id: "outings", name: "Outings", granted });

test("cada app dice si usa esta cuenta, otra o ninguna", () => {
  expect(grantLine(app(null), "a")).toBe("Sin permiso.");
  expect(grantLine(app({ app: "outings", connection: "b", label: "Trabajo", since: "2026-10-08T10:00:00Z" }), "a")).toBe(
    "La usa con tu cuenta «Trabajo».",
  );
  expect(grantLine(app({ app: "outings", connection: "a", label: "Personal", since: "2026-10-08T10:00:00Z" }), "a")).toBe(
    "La usa desde el 8 de octubre.",
  );
});

test("dar el permiso es ir a Hub, que lleva a Keycloak", () => {
  expect(authorizeClaudeRun("c1", "insights")).toBe("/api/hub/claude-run/authorize?connection=c1&app=insights");
});

test("con el relevo, una cuenta dice que cubre a la otra", () => {
  const elsewhere = app({ app: "insights", connection: "b", label: "Trabajo", since: "2026-10-08T10:00:00Z" });
  expect(grantLine(elsewhere, "a", true)).toBe("La usa con tu cuenta «Trabajo»; esta la cubre si aquella no puede.");
  expect(grantLine(elsewhere, "a", false)).toBe("La usa con tu cuenta «Trabajo».");
});
