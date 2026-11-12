import assert from "node:assert/strict";
import { test } from "node:test";

import { appearanceDeclarations, declaredClasses, isPlacement, unusedClasses } from "./css-rules.mjs";

test("colocar está permitido; el aspecto, no", () => {
  const css = `
.app-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  --app-columns: 2;
}
.app-title { font-size: var(--text-l); color: var(--fg); }
@media (min-width: 720px) {
  .app-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .app-card:hover { background: var(--surface-hover) }
}
`;
  assert.deepEqual(
    appearanceDeclarations(css).map((one) => one.property),
    ["font-size", "color", "background"],
  );
});

test("un comentario con dos puntos no es una declaración", () => {
  assert.deepEqual(appearanceDeclarations(".a { /* color: rojo */ display: flex; }"), []);
});

test("las propiedades personalizadas y la de colocación pasan", () => {
  assert.equal(isPlacement("--x"), true);
  assert.equal(isPlacement("padding-inline"), true);
  assert.equal(isPlacement("border-radius"), false);
});

test("las clases de un selector, y solo de selectores", () => {
  const classes = declaredClasses(".a, .b:hover {\n  width: 1.5rem;\n}\n.c .d { display: none }");
  assert.deepEqual([...classes.keys()], ["a", "b", "c", "d"]);
});

test("una clase sin uso se ve; una usada o de plantilla, no", () => {
  const css = ".app-used {} .app-dead {} .app-kind-strength {}";
  const sources = ['<div className="app-used" />', "const k = `app-kind-${kind}`;"];
  assert.deepEqual(unusedClasses(css, sources).map((one) => one.name), ["app-dead"]);
});
