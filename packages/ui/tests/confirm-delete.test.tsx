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
  it("says what is deleted and what is lost, and the button says what it does", () => {
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

  it("without a consequence, it warns that it cannot be undone", () => {
    mount(<ConfirmDelete title="¿Borrar?" action="Borrar" onCancel={() => undefined} onConfirm={() => undefined} />);

    expect(document.body.textContent).toContain(CANNOT_UNDO);
  });

  it("cancelling does not delete", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    mount(<ConfirmDelete title="¿Borrar?" action="Borrar" onCancel={onCancel} onConfirm={onConfirm} />);

    await press("Cancel");
    await press("Close");

    expect(onCancel).toHaveBeenCalledTimes(2);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("if the deletion fails, it says so in the sheet and allows retrying", async () => {
    const onConfirm = vi.fn().mockRejectedValueOnce(new Error("Offline")).mockResolvedValueOnce(undefined);
    mount(<ConfirmDelete title="¿Borrar?" action="Borrar" onCancel={() => undefined} onConfirm={onConfirm} />);

    await press("Borrar");
    expect(document.querySelector('[role="alert"]')?.textContent).toBe("Offline");

    await press("Borrar");
    expect(onConfirm).toHaveBeenCalledTimes(2);
    expect(document.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("CredentialField, when removing it", () => {
  it("asks first, and removes it only when confirmed", async () => {
    const onRemove = vi.fn();
    mount(
      <CredentialField
        label="Token for Claude Code"
        help="Lo generas con claude setup-token."
        configured
        hint="…a3f9"
        value=""
        onChange={() => undefined}
        onSave={() => undefined}
        onRemove={onRemove}
      />,
    );

    await press("Remove");
    const dialog = document.querySelector('[role="dialog"]');
    expect(onRemove).not.toHaveBeenCalled();
    expect(dialog?.getAttribute("aria-label")).toBe("Remove token for Claude Code?");
    expect(dialog?.textContent).toContain("Ends in a3f9");

    const confirm = Array.from(dialog?.querySelectorAll("button") ?? []).find((one) => one.textContent === "Remove");
    await act(async () => confirm?.click());

    expect(onRemove).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });
});
