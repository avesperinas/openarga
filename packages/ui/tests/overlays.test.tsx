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
  it("takes focus on open, returns it on close and Escape closes it", () => {
    function Page() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Abrir</button>
          {open && (
            <Sheet title="Add" onClose={() => setOpen(false)}>
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

  it("tab does not leave the sheet", () => {
    render(
      <Sheet title="Add" onClose={() => undefined}>
        <input aria-label="Nombre" />
      </Sheet>,
    );
    const sheet = document.querySelector<HTMLElement>(".bottom-sheet")!;
    const close = button("Close");
    const field = document.querySelector<HTMLInputElement>("input")!;
    field.focus();
    key(sheet, "Tab");
    expect(document.activeElement).toBe(close);
    key(sheet, "Tab", { shiftKey: true });
    expect(document.activeElement).toBe(field);
  });

  it("dragged down more than a quarter it closes; a little, it does not", () => {
    const onClose = vi.fn();
    render(
      <Sheet title="Add" onClose={onClose}>
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

describe("Sheet, what the review found", () => {
  it("if the opener does not let it close (it is saving), it slides back up instead of staying invisible", async () => {
    const proto = HTMLElement.prototype as { getAnimations?: () => unknown[] };
    proto.getAnimations = () => [];
    window.matchMedia = (() => ({ matches: false })) as never;
    try {
      render(
        <Sheet title="Delete?" onClose={() => undefined}>
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

  it("returns focus to the opener even with an autoFocus field inside", () => {
    function Page() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Abrir</button>
          {open && (
            <Sheet title="Add" onClose={() => setOpen(false)}>
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
  it("Escape closes only the topmost one", () => {
    const sheet = vi.fn();
    const dialog = vi.fn();
    render(
      <Sheet title="Hoja" onClose={sheet}>
        <Dialog title="Leave without saving?" onClose={dialog}>
          Se pierde lo escrito.
        </Dialog>
      </Sheet>,
    );
    key(window, "Escape");
    expect(dialog).toHaveBeenCalledTimes(1);
    expect(sheet).not.toHaveBeenCalled();
  });

  it("an alert does not close on outside tap", () => {
    const onClose = vi.fn();
    render(
      <Dialog title="Delete?" kind="alert" onClose={onClose} actions={[{ label: "Delete", onClick: () => undefined, tone: "danger" }]}>
        No se puede deshacer.
      </Dialog>,
    );
    expect(document.querySelector("[role=alertdialog]")).not.toBeNull();
    act(() => document.querySelector<HTMLElement>(".dialog-backdrop")!.click());
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("Menu", () => {
  it("the arrows walk, Enter chooses and focus returns to the button", () => {
    const edit = vi.fn();
    const remove = vi.fn();
    render(
      <Menu
        label="Book actions"
        items={[
          { label: "Editar", icon: "edit", onSelect: edit },
          { label: "Borrar", icon: "trash", onSelect: remove, tone: "danger" },
        ]}
      />,
    );
    const trigger = button("Book actions");
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
    { value: "es", label: "Spain" },
    { value: "fr", label: "Francia" },
    { value: "jp", label: "Japan" },
  ];

  it("filters ignoring accents and chooses with the arrows and Enter", () => {
    const onChange = vi.fn();
    render(<Combobox label="Country" options={options} value={null} onChange={onChange} />);
    const input = document.querySelector<HTMLInputElement>("input")!;
    act(() => input.focus());
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "japan");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(Array.from(document.querySelectorAll("[role=option]")).map((one) => one.textContent)).toEqual(["Japan"]);
    key(input, "Enter");
    expect(onChange).toHaveBeenCalledWith("jp");
  });

  it("with `create`, typed text that is not listed can also be chosen", () => {
    const onChange = vi.fn();
    render(<Combobox label="Country" options={options} value={null} onChange={onChange} create={(text) => `Add “${text}”`} />);
    const input = document.querySelector<HTMLInputElement>("input")!;
    act(() => input.focus());
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Iceland");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(document.querySelector("[role=option]")?.textContent).toBe("Add “Iceland”");
    key(input, "Enter");
    expect(onChange).toHaveBeenCalledWith("Iceland");
  });
});

describe("Combobox, what was created", () => {
  it("what was created stays written even if something was chosen before", () => {
    function Page() {
      const [value, setValue] = React.useState<string | null>("es");
      return (
        <Combobox
          label="Country"
          options={[{ value: "es", label: "Spain" }]}
          value={value}
          onChange={setValue}
          create={(text) => `Add “${text}”`}
        />
      );
    }
    render(<Page />);
    const input = document.querySelector<HTMLInputElement>("input")!;
    act(() => input.focus());
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Iceland");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    key(input, "Enter");
    expect(input.value).toBe("Iceland");
  });
});

describe("Tabs", () => {
  it("the arrows move between tabs and only the chosen one is in the tab order", () => {
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
  it("Enter runs the choice, arrows choose and Escape closes", () => {
    const run = { today: vi.fn(), week: vi.fn() };
    const onClose = vi.fn();
    render(
      <CommandPalette
        label="Comandos"
        placeholder="What do you want to do"
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

  it("commands match ignoring accents, and ⌘K opens", () => {
    expect(matching([{ label: "Go to today" }, { label: "New can\u00e7\u00f3n" }], "cancon")).toEqual([{ label: "New can\u00e7\u00f3n" }]);
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
  it("the actions are there for the keyboard without swiping", () => {
    const remove = vi.fn();
    render(
      <SwipeRow label="Leche" actions={[{ label: "Remove", icon: "trash", tone: "danger", onAction: remove }]}>
        <p>Leche</p>
      </SwipeRow>,
    );
    const action = button("Remove");
    act(() => action.focus());
    expect(document.querySelector(".swipe-row")?.hasAttribute("data-open")).toBe(true);
    act(() => action.click());
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it("where it rests on release: closed, open or the first action done", () => {
    expect(swipeEnd(-20, 360, 1)).toBe("closed");
    expect(swipeEnd(-80, 360, 1)).toBe("open");
    expect(swipeEnd(-260, 360, 1)).toBe("full");
    expect(pullDistance(100)).toBe(50);
    expect(pullDistance(-30)).toBe(0);
  });

  it("a sideways swipe turns the page only with a real gesture, each side its own", () => {
    expect(pageSwipe(300, 280)).toBeNull();
    expect(pageSwipe(300, 150)).toBe("next");
    expect(pageSwipe(100, 260)).toBe("previous");
  });
});

describe("the rest", () => {
  it("offline it says so; online it takes no space", () => {
    const online = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(<OfflineNotice pending={2} />);
    expect(document.body.textContent).toContain("Offline");
    expect(document.body.textContent).toContain("2 changes waiting to be sent.");
    online.mockReturnValue(true);
    act(() => window.dispatchEvent(new Event("online")));
    expect(document.body.textContent).not.toContain("Offline");
    online.mockRestore();
  });

  it("a popover goes below the button, and above if it does not fit below", () => {
    const anchor = { top: 700, bottom: 740, left: 300, right: 340 } as DOMRect;
    expect(placeNear(anchor, { width: 200, height: 150 }, { width: 390, height: 800 })).toEqual({ top: 542, left: 182, above: true });
    expect(placeNear({ ...anchor, top: 100, bottom: 140 } as DOMRect, { width: 200, height: 150 }, { width: 390, height: 800 }).above).toBe(false);
  });

  it("the initials, each person's tone and an invalid range", () => {
    expect(initials("Ana Mar\u00eda L\u00f3pez")).toBe("AL");
    expect(initials("  ")).toBe("?");
    expect(toneOf("Ana")).toBe(toneOf("Ana"));
    expect(toneOf("Ana")).toBeGreaterThanOrEqual(1);
    expect(rangeProblem({ from: "2026-10-10", to: "2026-10-01" })).toBe("The end comes before the start.");
    expect(rangeProblem({ from: "", to: "2026-10-01" })).toBeNull();
  });
});
