// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ConfirmChange, ConfirmPanel } from "../src/index";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.innerHTML = "";
});

function mount(node: React.ReactNode): void {
  const host = document.createElement("div");
  document.body.append(host);
  act(() => createRoot(host).render(node));
}

async function press(name: string): Promise<void> {
  const found = Array.from(document.querySelectorAll("button")).find((b) => b.textContent === name);
  if (!found) throw new Error(`no hay botón "${name}"`);
  await act(async () => found.click());
}

describe("confirmar un cambio", () => {
  it("dice qué cambia y no guarda hasta que se pulsa su botón", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    mount(
      <ConfirmPanel
        title="¿Guardar?"
        changes={[{ label: "Categoría", from: "Ocio", to: "Salud" }]}
        action="Guardar cambios"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );
    expect(document.body.textContent).toContain("Ocio");
    expect(document.body.textContent).toContain("Salud");
    expect(onConfirm).not.toHaveBeenCalled();
    await press("Volver");
    expect(onCancel).toHaveBeenCalledOnce();
    await press("Guardar cambios");
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("si falla, lo dice y deja reintentar", async () => {
    mount(
      <ConfirmChange title="¿Liquidar?" action="Marcar como liquidado" onCancel={() => undefined} onConfirm={() => Promise.reject(new Error("Sin conexión"))} />,
    );
    await press("Marcar como liquidado");
    expect(document.querySelector('[role="alert"]')?.textContent).toBe("Sin conexión");
    expect(Array.from(document.querySelectorAll("button")).some((b) => b.textContent === "Marcar como liquidado")).toBe(true);
  });
});
