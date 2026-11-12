// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import {
  Combobox,
  CommandPalette,
  Dialog,
  Menu,
  OfflineNotice,
  Sheet,
  SwipeRow,
  Tabs,
  initials,
  matching,
  placeNear,
  pageSwipe,
  pullDistance,
  rangeProblem,
  swipeEnd,
  toneOf,
  useShortcut,
} from "../src/index";

let root: Root;
let host: HTMLElement;

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});
beforeEach(() => {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  document.body.innerHTML = "";
});

const render = (node: React.ReactNode) => act(() => root.render(node));
const key = (target: EventTarget, name: string, extra: KeyboardEventInit = {}) =>
  act(() => {
    target.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, ...extra }));
  });
const button = (name: string) =>
  Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(
    (one) => one.getAttribute("aria-label") === name || one.textContent?.trim() === name,
  )!;

describe("Sheet", () => {
  it("se lleva el foco al abrir, lo devuelve al cerrar y Escape la cierra", () => {
    function Page() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Abrir</button>
          {open && (
            <Sheet title="Añadir" onClose={() => setOpen(false)}>
              <input aria-label="Nombre" />
            </Sheet>
          )}
        </>
      );
    }
    render(<Page />);
    const opener = button("Abrir");
    opener.focus();
    act(() => opener.click());
    expect(document.querySelector(".bottom-sheet")?.contains(document.activeElement)).toBe(true);

    key(window, "Escape");
    expect(document.querySelector(".bottom-sheet")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("el tabulador no sale de la hoja", () => {
    render(
      <Sheet title="Añadir" onClose={() => undefined}>
        <input aria-label="Nombre" />
      </Sheet>,
    );
    const sheet = document.querySelector<HTMLElement>(".bottom-sheet")!;
    const close = button("Cerrar");
    const field = document.querySelector<HTMLInputElement>("input")!;
    field.focus();
    key(sheet, "Tab");
    expect(document.activeElement).toBe(close);
    key(sheet, "Tab", { shiftKey: true });
    expect(document.activeElement).toBe(field);
  });

  it("arrastrada hacia abajo más de un cuarto se cierra; un poco, no", () => {
    const onClose = vi.fn();
    render(
      <Sheet title="Añadir" onClose={onClose}>
        <p>Algo</p>
      </Sheet>,
    );
    const sheet = document.querySelector<HTMLElement>(".bottom-sheet")!;
    sheet.getBoundingClientRect = () => ({ height: 400 }) as DOMRect;
    const head = document.querySelector<HTMLElement>(".bottom-sheet-head")!;
    const drag = (to: number, ms: number) =>
      act(() => {
        const down = new PointerEvent("pointerdown", { clientY: 0, bubbles: true });
        Object.defineProperty(down, "timeStamp", { value: 1000 });
        head.dispatchEvent(down);
        head.dispatchEvent(new PointerEvent("pointermove", { clientY: to, bubbles: true }));
        const up = new PointerEvent("pointerup", { clientY: to, bubbles: true });
        Object.defineProperty(up, "timeStamp", { value: ms });
        head.dispatchEvent(up);
      });
    drag(40, 1400);
    expect(onClose).not.toHaveBeenCalled();
    drag(160, 1400);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("Sheet, lo que encontró la revisión", () => {
  it("si quien la abrió no la deja cerrar (está guardando), vuelve a subir en vez de quedarse invisible", async () => {
    const proto = HTMLElement.prototype as { getAnimations?: () => unknown[] };
    proto.getAnimations = () => [];
    window.matchMedia = (() => ({ matches: false })) as never;
    try {
      render(
        <Sheet title="¿Borrar?" onClose={() => undefined}>
          <p>Borrando…</p>
        </Sheet>,
      );
      key(window, "Escape");
      const sheet = document.querySelector<HTMLElement>(".bottom-sheet")!;
      expect(sheet.hasAttribute("data-leaving")).toBe(true);
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 650));
      });
      expect(sheet.hasAttribute("data-leaving")).toBe(false);
    } finally {
      delete proto.getAnimations;
    }
  });

  it("devuelve el foco a quien la abrió aunque dentro haya un campo con autoFocus", () => {
    function Page() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Abrir</button>
          {open && (
            <Sheet title="Añadir" onClose={() => setOpen(false)}>
              <input aria-label="Nombre" autoFocus />
            </Sheet>
          )}
        </>
      );
    }
    render(<Page />);
    const opener = button("Abrir");
    opener.focus();
    act(() => opener.click());
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Nombre");
    key(window, "Escape");
    expect(document.activeElement).toBe(opener);
  });
});

describe("Dialog", () => {
  it("Escape cierra solo lo de más arriba", () => {
    const sheet = vi.fn();
    const dialog = vi.fn();
    render(
      <Sheet title="Hoja" onClose={sheet}>
        <Dialog title="¿Salir sin guardar?" onClose={dialog}>
          Se pierde lo escrito.
        </Dialog>
      </Sheet>,
    );
    key(window, "Escape");
    expect(dialog).toHaveBeenCalledTimes(1);
    expect(sheet).not.toHaveBeenCalled();
  });

  it("una alerta no se cierra tocando fuera", () => {
    const onClose = vi.fn();
    render(
      <Dialog title="¿Borrar?" kind="alert" onClose={onClose} actions={[{ label: "Borrar", onClick: () => undefined, tone: "danger" }]}>
        No se puede deshacer.
      </Dialog>,
    );
    expect(document.querySelector("[role=alertdialog]")).not.toBeNull();
    act(() => document.querySelector<HTMLElement>(".dialog-backdrop")!.click());
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("Menu", () => {
  it("las flechas recorren, Intro elige y el foco vuelve al botón", () => {
    const edit = vi.fn();
    const remove = vi.fn();
    render(
      <Menu
        label="Acciones del libro"
        items={[
          { label: "Editar", icon: "edit", onSelect: edit },
          { label: "Borrar", icon: "trash", onSelect: remove, tone: "danger" },
        ]}
      />,
    );
    const trigger = button("Acciones del libro");
    trigger.focus();
    act(() => trigger.click());
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement?.textContent).toBe("Editar");

    key(document.activeElement!, "ArrowDown");
    expect(document.activeElement?.textContent).toBe("Borrar");
    act(() => (document.activeElement as HTMLButtonElement).click());
    expect(remove).toHaveBeenCalledTimes(1);
    expect(edit).not.toHaveBeenCalled();
    expect(document.querySelector("[role=menu]")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("Combobox", () => {
  const options = [
    { value: "es", label: "España" },
    { value: "fr", label: "Francia" },
    { value: "jp", label: "Japón" },
  ];

  it("filtra sin tildes y elige con las flechas e Intro", () => {
    const onChange = vi.fn();
    render(<Combobox label="País" options={options} value={null} onChange={onChange} />);
    const input = document.querySelector<HTMLInputElement>("input")!;
    act(() => input.focus());
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "japon");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(Array.from(document.querySelectorAll("[role=option]")).map((one) => one.textContent)).toEqual(["Japón"]);
    key(input, "Enter");
    expect(onChange).toHaveBeenCalledWith("jp");
  });

  it("con `create`, lo escrito que no está también se elige", () => {
    const onChange = vi.fn();
    render(<Combobox label="País" options={options} value={null} onChange={onChange} create={(text) => `Añadir «${text}»`} />);
    const input = document.querySelector<HTMLInputElement>("input")!;
    act(() => input.focus());
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Islandia");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(document.querySelector("[role=option]")?.textContent).toBe("Añadir «Islandia»");
    key(input, "Enter");
    expect(onChange).toHaveBeenCalledWith("Islandia");
  });
});

describe("Combobox, lo creado", () => {
  it("lo creado se queda escrito aunque antes hubiera algo elegido", () => {
    function Page() {
      const [value, setValue] = React.useState<string | null>("es");
      return (
        <Combobox
          label="País"
          options={[{ value: "es", label: "España" }]}
          value={value}
          onChange={setValue}
          create={(text) => `Añadir «${text}»`}
        />
      );
    }
    render(<Page />);
    const input = document.querySelector<HTMLInputElement>("input")!;
    act(() => input.focus());
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Islandia");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    key(input, "Enter");
    expect(input.value).toBe("Islandia");
  });
});

describe("Tabs", () => {
  it("las flechas pasan de una pestaña a otra y solo la elegida está en el tabulador", () => {
    function Page() {
      const [active, setActive] = React.useState<"a" | "b" | "c">("a");
      return (
        <Tabs
          label="Vistas"
          active={active}
          onSelect={setActive}
          items={[
            { id: "a", label: "Resumen" },
            { id: "b", label: "Movimientos", count: 3 },
            { id: "c", label: "Presupuesto" },
          ]}
        />
      );
    }
    render(<Page />);
    const tabs = () => Array.from(document.querySelectorAll<HTMLButtonElement>("[role=tab]"));
    key(tabs()[0]!, "ArrowLeft");
    expect(tabs().map((one) => one.getAttribute("aria-selected"))).toEqual(["false", "false", "true"]);
    expect(tabs().map((one) => one.tabIndex)).toEqual([-1, -1, 0]);
  });
});

describe("CommandPalette", () => {
  it("Intro hace lo elegido, las flechas eligen y Escape cierra", () => {
    const run = { today: vi.fn(), week: vi.fn() };
    const onClose = vi.fn();
    render(
      <CommandPalette
        label="Comandos"
        placeholder="Qué quieres hacer"
        query=""
        onQuery={() => undefined}
        onClose={onClose}
        groups={[
          {
            label: "Comandos",
            items: [
              { key: "today", label: "Ir a hoy", icon: "today", shortcut: "T", run: run.today },
              { key: "week", label: "Ver la semana", icon: "calendar", run: run.week },
            ],
          },
        ]}
      />,
    );
    const input = document.querySelector<HTMLInputElement>(".palette-input")!;
    expect(document.activeElement).toBe(input);
    key(input, "ArrowDown");
    key(input, "Enter");
    expect(run.week).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    key(window, "Escape");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("los comandos casan sin tildes, y ⌘K abre", () => {
    expect(matching([{ label: "Ir a hoy" }, { label: "Nueva canción" }], "cancion")).toEqual([{ label: "Nueva canción" }]);
    const open = vi.fn();
    function Page() {
      useShortcut("k", open);
      return null;
    }
    render(<Page />);
    key(window, "k", { metaKey: true });
    key(window, "k");
    expect(open).toHaveBeenCalledTimes(1);
  });
});

describe("SwipeRow", () => {
  it("las acciones están para el teclado sin deslizar nada", () => {
    const remove = vi.fn();
    render(
      <SwipeRow label="Leche" actions={[{ label: "Quitar", icon: "trash", tone: "danger", onAction: remove }]}>
        <p>Leche</p>
      </SwipeRow>,
    );
    const action = button("Quitar");
    act(() => action.focus());
    expect(document.querySelector(".swipe-row")?.hasAttribute("data-open")).toBe(true);
    act(() => action.click());
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it("dónde queda al soltar: cerrada, abierta o la primera acción hecha", () => {
    expect(swipeEnd(-20, 360, 1)).toBe("closed");
    expect(swipeEnd(-80, 360, 1)).toBe("open");
    expect(swipeEnd(-260, 360, 1)).toBe("full");
    expect(pullDistance(100)).toBe(50);
    expect(pullDistance(-30)).toBe(0);
  });

  it("deslizar de lado pasa de página solo con un gesto de verdad, y a cada lado lo suyo", () => {
    expect(pageSwipe(300, 280)).toBeNull();
    expect(pageSwipe(300, 150)).toBe("next");
    expect(pageSwipe(100, 260)).toBe("previous");
  });
});

describe("lo demás", () => {
  it("sin red lo dice; con red no ocupa nada", () => {
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(<OfflineNotice pending={2} />);
    expect(document.body.textContent).toContain("Sin conexión");
    expect(document.body.textContent).toContain("2 cambios por enviar.");
    online.mockReturnValue(true);
    act(() => window.dispatchEvent(new Event("online")));
    expect(document.body.textContent).not.toContain("Sin conexión");
    online.mockRestore();
  });

  it("un globo va debajo del botón, y encima si abajo no cabe", () => {
    const anchor = { top: 700, bottom: 740, left: 300, right: 340 } as DOMRect;
    expect(placeNear(anchor, { width: 200, height: 150 }, { width: 390, height: 800 })).toEqual({ top: 542, left: 182, above: true });
    expect(placeNear({ ...anchor, top: 100, bottom: 140 } as DOMRect, { width: 200, height: 150 }, { width: 390, height: 800 }).above).toBe(false);
  });

  it("las iniciales, el tono de cada persona y un rango que no vale", () => {
    expect(initials("Ana María López")).toBe("AL");
    expect(initials("  ")).toBe("?");
    expect(toneOf("Ana")).toBe(toneOf("Ana"));
    expect(toneOf("Ana")).toBeGreaterThanOrEqual(1);
    expect(rangeProblem({ from: "2026-10-10", to: "2026-10-01" })).toBe("El final va antes del principio.");
    expect(rangeProblem({ from: "", to: "2026-10-01" })).toBeNull();
  });
});
