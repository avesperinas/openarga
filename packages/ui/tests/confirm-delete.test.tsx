// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { CANNOT_UNDO, ConfirmDelete, CredentialField } from "../src/index";

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

function button(name: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll("button")).find(
    (candidate) => candidate.textContent === name || candidate.getAttribute("aria-label") === name,
  );
  if (!found) throw new Error(`no hay botón "${name}"`);
  return found;
}

async function press(name: string): Promise<void> {
  await act(async () => {
    button(name).click();
  });
}

describe("ConfirmDelete", () => {
  it("dice qué se borra y qué se pierde, y el botón dice lo que hace", () => {
    mount(
      <ConfirmDelete
        title="¿Borrar esta receta?"
        subject="Lentejas"
        consequence="Se pierden sus 3 pasos."
        action="Borrar receta"
        onCancel={() => undefined}
        onConfirm={() => undefined}
      />,
    );
    const dialog = document.querySelector('[role="dialog"]');

    expect(dialog?.getAttribute("aria-label")).toBe("¿Borrar esta receta?");
    expect(dialog?.textContent).toContain("Lentejas");
    expect(dialog?.textContent).toContain("Se pierden sus 3 pasos.");
    expect(button("Borrar receta").dataset.variant).toBe("destructive");
  });

  it("sin consecuencia, avisa de que no se puede deshacer", () => {
    mount(<ConfirmDelete title="¿Borrar?" action="Borrar" onCancel={() => undefined} onConfirm={() => undefined} />);

    expect(document.body.textContent).toContain(CANNOT_UNDO);
  });

  it("cancelar no borra", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    mount(<ConfirmDelete title="¿Borrar?" action="Borrar" onCancel={onCancel} onConfirm={onConfirm} />);

    await press("Cancelar");
    await press("Cerrar");

    expect(onCancel).toHaveBeenCalledTimes(2);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("si el borrado falla, lo dice en la hoja y deja reintentar", async () => {
    const onConfirm = vi.fn().mockRejectedValueOnce(new Error("Sin conexión")).mockResolvedValueOnce(undefined);
    mount(<ConfirmDelete title="¿Borrar?" action="Borrar" onCancel={() => undefined} onConfirm={onConfirm} />);

    await press("Borrar");
    expect(document.querySelector('[role="alert"]')?.textContent).toBe("Sin conexión");

    await press("Borrar");
    expect(onConfirm).toHaveBeenCalledTimes(2);
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("CredentialField, al quitarla", () => {
  it("pregunta antes, y solo la quita al confirmarlo", async () => {
    const onRemove = vi.fn();
    mount(
      <CredentialField
        label="Token de Claude Code"
        help="Lo generas con claude setup-token."
        configured
        hint="…a3f9"
        value=""
        onChange={() => undefined}
        onSave={() => undefined}
        onRemove={onRemove}
      />,
    );

    await press("Quitar");
    const dialog = document.querySelector('[role="dialog"]');
    expect(onRemove).not.toHaveBeenCalled();
    expect(dialog?.getAttribute("aria-label")).toBe("¿Quitar token de Claude Code?");
    expect(dialog?.textContent).toContain("Termina en a3f9");

    const confirm = Array.from(dialog?.querySelectorAll("button") ?? []).find((one) => one.textContent === "Quitar");
    await act(async () => confirm?.click());

    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });
});
