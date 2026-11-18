import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  AppBar,
  Button,
  CheckRow,
  ChoiceChips,
  ConfirmButton,
  CopyField,
  CredentialField,
  Elapsed,
  IconButton,
  LevelChips,
  List,
  ListRow,
  MonthCalendar,
  SegmentedControl,
  Sheet,
  Slider,
  Stepper,
  Switch,
  SyncMark,
  TabBar,
  TextField,
  VersionTag,
  WallpaperPicker,
  formatDecimal,
  formatElapsed,
  isoDay,
  monthWeeks,
  nextLevel,
  parseDecimal,
  segmentFor,
  sliderFill,
  stepValue,
} from "../src/index";

const render = (element: React.ReactElement): string => renderToStaticMarkup(element);
const noop = () => {};

describe("Button", () => {
  it("is secondary by default and never submits a form unasked", () => {
    const html = render(<Button onClick={noop}>Cancelar</Button>);
    expect(html).toContain('data-variant="secondary"');
    expect(html).toContain('type="button"');
  });

  it("carries the variant, size and width asked of it", () => {
    const html = render(
      <Button variant="destructive" size="small" block icon="trash">
        Borrar
      </Button>,
    );
    expect(html).toContain('data-variant="destructive"');
    expect(html).toContain('data-size="small"');
    expect(html).toContain("data-block");
    expect(html).toContain('class="icon"');
  });
});

describe("IconButton", () => {
  it("announces itself with its label and the icon stays decorative", () => {
    const html = render(<IconButton icon="close" label="Close" onClick={noop} />);
    expect(html).toContain('aria-label="Close"');
    expect(html).toContain('aria-hidden="true"');
  });
});

describe("SegmentedControl", () => {
  const options = [
    { value: "system", label: "Sistema", icon: "system" },
    { value: "light", label: "Claro", icon: "sun" },
    { value: "dark", label: "Oscuro", icon: "moon" },
  ] as const;

  const html = render(
    <SegmentedControl label="Tema" options={[...options]} value="light" onChange={noop} />,
  );

  it("is a radio group with a single chosen one", () => {
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-label="Tema"');
    expect(html.match(/role="radio"/g)).toHaveLength(3);
    expect(html.match(/aria-checked="true"/g)).toHaveLength(1);
  });

  it("only the chosen one enters the tab order", () => {
    expect(html.match(/tabindex="0"/g)).toHaveLength(1);
    expect(html.match(/tabindex="-1"/g)).toHaveLength(2);
  });

  it("the thumb knows how many segments there are and which to go to", () => {
    expect(html).toContain("--segments:3");
    expect(html).toContain("--selected:1");
  });

  it("with a value not in the list, the thumb does not leave the track", () => {
    const stray = render(
      <SegmentedControl label="Tema" options={[...options]} value={"sepia" as never} onChange={noop} />,
    );
    expect(stray).toContain("--selected:0");
  });

  it("can stay icons-only on a narrow screen without losing the name", () => {
    const narrow = render(
      <SegmentedControl label="Tema" options={[...options]} value="light" onChange={noop} iconsWhenNarrow />,
    );
    expect(narrow).toContain("data-icons-narrow");
    expect(narrow).toContain('<span class="segmented-label">Claro</span>');
    expect(html).not.toContain("data-icons-narrow");
  });
});

describe("segmentFor", () => {
  it("the arrows advance and wrap at the ends", () => {
    expect(segmentFor("ArrowRight", 0, 3)).toBe(1);
    expect(segmentFor("ArrowRight", 2, 3)).toBe(0);
    expect(segmentFor("ArrowLeft", 0, 3)).toBe(2);
    expect(segmentFor("ArrowDown", 1, 3)).toBe(2);
  });

  it("Home and End go to the ends and other keys move nothing", () => {
    expect(segmentFor("Home", 2, 3)).toBe(0);
    expect(segmentFor("End", 0, 3)).toBe(2);
    expect(segmentFor("a", 1, 3)).toBeNull();
    expect(segmentFor("ArrowRight", 0, 0)).toBeNull();
  });
});

describe("Slider", () => {
  it("fills the stretch up to the value and announces the text, not the raw number", () => {
    const html = render(
      <Slider
        label="Transparencia"
        min={0.2}
        max={1}
        step={0.05}
        value={0.6}
        valueText="60 por ciento"
        onChange={noop}
      />,
    );
    expect(html).toContain("--fill-to:50%");
    expect(html).toContain('aria-valuetext="60 por ciento"');
  });

  it("the fill is clipped to the track", () => {
    expect(sliderFill(2, 0, 1)).toBe(100);
    expect(sliderFill(-1, 0, 1)).toBe(0);
    expect(sliderFill(1, 1, 1)).toBe(0);
  });
});

describe("List", () => {
  it("each row goes in its list item, and disabled ones stay in place", () => {
    const html = render(
      <List>
        <ListRow title="Eventos" detail="Ya colocado" hue={1} accessory="done" disabled />
        <ListRow title="Demo" detail="2x2" hue={5} accessory="plus" onClick={noop} />
      </List>,
    );
    expect(html.match(/<li>/g)).toHaveLength(2);
    expect(html).toContain("disabled");
    expect(html).toContain('data-hue="5"');
  });

  it("with a second line and a figure, the name and what it is stack and the amount sits apart", () => {
    const html = render(
      <ListRow title="Alba Supermarket" subtitle="Uncategorised" value="−60,00 €" tone="warning" onClick={noop} />,
    );
    expect(html).toContain('class="list-row-text"');
    expect(html).toContain('<span class="list-row-subtitle">Uncategorised</span>');
    expect(html).toContain('<span class="list-row-value">−60,00 €</span>');
    expect(html).toContain('data-tone="warning"');
  });

  it("without a second line, the row is the usual one", () => {
    const html = render(<ListRow title="Demo" detail="2x2" onClick={noop} />);
    expect(html).not.toContain("list-row-text");
    expect(html).not.toContain("list-row-value");
  });
});

describe("CheckRow", () => {
  it("is a checkbox that says whether it is checked, and the whole row is the target", () => {
    const html = render(<CheckRow title="Leche" detail="2" checked onToggle={noop} />);
    expect(html).toContain('role="checkbox"');
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("data-checked");
    expect(html).toContain("Leche");
    expect(html).not.toContain("check-row-more");
  });

  it("anything other than ticking goes in its own button, and that button has a name", () => {
    const html = render(
      <CheckRow title="Pan" checked={false} onToggle={noop} more={{ label: "Cambiar pan", onClick: noop }} />,
    );
    expect(html).toContain('aria-checked="false"');
    expect(html).not.toContain("data-checked");
    expect(html).toContain('aria-label="Cambiar pan"');
  });
});

describe("Stepper", () => {
  it("small, for a row: it says so for the CSS and is still the same named group (T-B05)", () => {
    const html = render(<Stepper size="small" label="Reps" value={8} step={1} onChange={noop} />);
    expect(html).toContain('data-size="small"');
    expect(html).toContain('aria-label="Reps"');
    expect(render(<Stepper label="Reps" value={8} step={1} onChange={noop} />)).not.toContain("data-size");
  });

  it("steps up and down without accumulating floating point error", () => {
    let value = 60;
    for (let i = 0; i < 7; i++) value = stepValue(value, 2.5, 1);
    expect(value).toBe(77.5);
    expect(stepValue(0.3, 0.1, 1)).toBe(0.4);
  });

  it("does not go below the minimum or above the maximum", () => {
    expect(stepValue(1, 2.5, -1, 0)).toBe(0);
    expect(stepValue(99, 5, 1, 0, 100)).toBe(100);
  });

  it("without a value, the first tap starts at the minimum instead of adding to nothing", () => {
    expect(stepValue(null, 2.5, 1, 20)).toBe(20);
  });

  it("reads the decimal comma of a Spanish keyboard, and empty is not zero", () => {
    expect(parseDecimal("62,5")).toBe(62.5);
    expect(parseDecimal(" 17.5 ")).toBe(17.5);
    expect(parseDecimal("")).toBeNull();
    expect(parseDecimal("abc")).toBeNull();
  });

  it("writes 60 and 62.5, without padding decimals", () => {
    expect(formatDecimal(60)).toBe("60");
    expect(formatDecimal(62.5)).toBe("62.5");
    expect(formatDecimal(null)).toBe("—");
  });

  it("is a named group, and its buttons say what they change", () => {
    const html = render(<Stepper label="Weight" value={60} step={2.5} unit="kg" onChange={noop} />);
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="Less weight"');
    expect(html).toContain('aria-label="More weight"');
    expect(html).not.toContain("<input");
  });

  it("at the minimum the decrease button turns off", () => {
    const html = render(<Stepper label="Reps" value={0} step={1} onChange={noop} />);
    expect(html).toMatch(/aria-label="Less reps" disabled/);
  });
});

describe("ChoiceChips", () => {
  it("is a radio group with the chosen one checked", () => {
    const html = render(
      <ChoiceChips
        label="Variante"
        value="smith"
        options={[
          { value: "smith", label: "Sentadilla Smith" },
          { value: "prensa", label: "Prensa" },
        ]}
        onChange={noop}
      />,
    );
    expect(html).toContain('role="radiogroup"');
    expect(html.match(/aria-checked="true"/g)).toHaveLength(1);
  });
});

describe("Elapsed", () => {
  it("counts minutes and seconds, and hours when there are some", () => {
    expect(formatElapsed(7_000)).toBe("0:07");
    expect(formatElapsed(750_000)).toBe("12:30");
    expect(formatElapsed(3_902_000)).toBe("1:05:02");
  });

  it("a clock running ahead gives no negative time", () => {
    expect(formatElapsed(-5_000)).toBe("0:00");
  });

  it("without a start date it does not invent a zero", () => {
    const html = render(<Elapsed since={null} label="Descanso" now={0} />);
    expect(html).toContain("—");
  });
});

describe("SyncMark and ConfirmButton", () => {
  it("the sending state is announced, not only coloured", () => {
    expect(render(<SyncMark state="pending" />)).toContain('aria-label="Waiting to be sent"');
    expect(render(<SyncMark state="saved" />)).toContain('aria-label="Saved"');
  });

  it("confirm says whether it is already confirmed", () => {
    expect(render(<ConfirmButton label="Confirmar serie 1" confirmed />)).toContain(
      'aria-pressed="true"',
    );
  });
});

describe("AppBar", () => {
  it("accepts actions and not nodes", () => {
    const html = render(
      <AppBar
        title="Pull"
        subtitle="Rotation 3"
        back={{ icon: "chevron-left", label: "Back", onClick: noop }}
        action={{ label: "Terminar", onClick: noop }}
      />,
    );
    expect(html).toContain("Pull");
    expect(html).toContain('aria-label="Back"');
    expect(html).toContain("Terminar");
  });
});

describe("MonthCalendar", () => {
  it("weeks run Monday to Sunday, with gaps before the 1st", () => {
    const weeks = monthWeeks(2026, 8);
    expect(weeks).toHaveLength(5);
    expect(weeks[0]?.monday).toBe("2026-08-31");
    expect(weeks[0]?.cells[0]).toBeNull();
    expect(weeks[0]?.cells[1]).toEqual({ day: "2026-09-01", date: 1 });
    expect(weeks[4]?.cells.filter(Boolean)).toHaveLength(3);
  });

  it("with a week label, each row carries its own on the left", () => {
    const html = render(
      <MonthCalendar
        year={2026}
        month={8}
        marks={{}}
        today="2026-09-16"
        onPrevious={noop}
        onNext={noop}
        weekLabel={(monday) => (monday === "2026-09-07" ? "R12" : null)}
      />,
    );
    expect(html).toContain('data-labelled=""');
    expect(html.match(/class="month-week-label"/g)).toHaveLength(6);
    expect(html).toContain(">R12</span>");
  });

  it("empty, it renders whole, with today marked", () => {
    const html = render(
      <MonthCalendar year={2026} month={8} marks={{}} today="2026-09-16" onPrevious={noop} onNext={noop} />,
    );
    expect(html).toContain("September 2026");
    expect(html.match(/role="gridcell"/g)).toHaveLength(30);
    expect(html).toMatch(/data-today="true"[^>]*aria-label="Wednesday 16 September"/);
  });

  it("a day with a workout carries its kind and says it", () => {
    const html = render(
      <MonthCalendar
        year={2026}
        month={8}
        marks={{ "2026-09-14": [{ kind: "pull", label: "Pull, 52 min" }] }}
        today="2026-09-16"
        onPrevious={noop}
        onNext={noop}
      />,
    );
    expect(html).toMatch(/data-marked="true" data-kind="pull"[^>]*aria-label="Monday 14 September: Pull, 52 min"/);
  });

  it("the local day does not shift with the time zone", () => {
    expect(isoDay(new Date(2026, 0, 1, 0, 30))).toBe("2026-01-01");
  });
});

describe("VersionTag", () => {
  it("shows what it is and which version runs, without decoration", () => {
    const html = render(<VersionTag name="training" version="v1.2.0" />);
    expect(html).toContain("training");
    expect(html).toContain("v1.2.0");
  });
});

describe("TabBar, Sheet and TextField", () => {
  it("the active tab announces itself as the current page", () => {
    const html = render(
      <TabBar
        label="Secciones"
        active="plan"
        onSelect={noop}
        items={[
          { id: "today", label: "Today", icon: "today" },
          { id: "plan", label: "Plan", icon: "edit" },
        ]}
      />,
    );
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-current="page"[^>]*>.*Plan/);
  });

  it("the sheet is a named dialog with its action", () => {
    const html = render(
      <Sheet title="Add exercise" onClose={noop} action={{ label: "Add", onClick: noop }}>
        <p>contenido</p>
      </Sheet>,
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="Add exercise"');
    expect(html).toContain("Add</span></button>");
  });

  it("without an action, the body is last and leaves room for the phone's home bar", () => {
    const html = render(
      <Sheet title="Start Pull?" onClose={noop}>
        <button type="button">Empezar</button>
      </Sheet>,
    );
    expect(html).not.toContain("bottom-sheet-foot");

    const css = readFileSync(new URL("../controls.css", import.meta.url), "utf8");
    const rule = /\.bottom-sheet-body:last-child \{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(rule).toContain("env(safe-area-inset-bottom)");
  });

  it("the field is tied to its label and its hint", () => {
    const html = render(<TextField label="Nombre" value="" onChange={noop} hint="Obligatorio" invalid />);
    const id = /for="([^"]+)"/.exec(html)?.[1];
    expect(html).toContain(`id="${id}"`);
    expect(html).toContain(`aria-describedby="${id}-hint"`);
    expect(html).toContain('aria-invalid="true"');
  });
});

describe("LevelChips", () => {
  const LEVELS = [
    { value: "primary", label: "primary" },
    { value: "secondary", label: "secondary" },
  ] as const;

  it("tapping cycles primary, secondary and unchosen", () => {
    const levels = [...LEVELS];
    expect(nextLevel(levels, undefined)).toBe("primary");
    expect(nextLevel(levels, "primary")).toBe("secondary");
    expect(nextLevel(levels, "secondary")).toBeUndefined();
  });

  it("the level is announced and visible, not only coloured", () => {
    const html = render(
      <LevelChips
        label="Muscles"
        levels={[...LEVELS]}
        value={{ chest: "primary", triceps: "secondary" }}
        onChange={noop}
        options={[
          { value: "chest", label: "Chest" },
          { value: "triceps", label: "Triceps" },
          { value: "lats", label: "Lats" },
        ]}
      />,
    );
    expect(html).toContain('aria-label="Chest: primary"');
    expect(html).toContain('aria-label="Triceps: secondary"');
    expect(html).toMatch(/aria-pressed="false" aria-label="Lats"/);
    expect(html).toContain("secondary</span>");
  });
});

describe("WallpaperPicker", () => {
  it("marks the chosen one, and following the inherited one is one more option", () => {
    const options = [
      { id: "marea", name: "Marea", image: "/wallpapers/marea.svg" },
      { id: "duna", name: "Duna", image: "/wallpapers/duna.svg" },
    ];
    const own = render(<WallpaperPicker label="Background" options={options} value="duna" onChange={noop} />);
    expect(own.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(own).toMatch(/aria-pressed="true"[^>]*url\(\/wallpapers\/duna.svg\)/);

    const inherited = render(
      <WallpaperPicker
        label="Background"
        options={options}
        value={null}
        onChange={noop}
        inherit={{ id: "marea", name: "El de arga", image: "/wallpapers/marea.svg" }}
      />,
    );
    expect(inherited).toMatch(/aria-pressed="true"[^>]*>.*El de arga/);
  });
});

describe("Switch", () => {
  it("is a named switch that says whether it is on", () => {
    const on = render(<Switch label="Programming" checked onChange={noop} />);
    const off = render(<Switch label="Programming" checked={false} onChange={noop} />);

    expect(on).toContain('role="switch"');
    expect(on).toContain('aria-label="Programming"');
    expect(on).toContain('aria-checked="true"');
    expect(off).toContain('aria-checked="false"');
    expect(on).toContain('type="button"');
  });
});

describe("CopyField", () => {
  it("shows the value without letting it be edited, and the button copies without sending anything", () => {
    const html = renderToStaticMarkup(<CopyField label="Client ID" value="claude" />);

    expect(html).toContain('readOnly=""');
    expect(html).toContain('value="claude"');
    expect(html).toContain('type="button"');
    expect(html).toContain('aria-label="Copy Client ID"');
    expect(html).toContain(">Copy<");
  });

  it("the label names the field", () => {
    const html = renderToStaticMarkup(<CopyField label="Server URL" value="https://x/mcp" />);
    const id = /<input id="([^"]+)"/.exec(html)?.[1];

    expect(id).toBeTruthy();
    expect(html).toContain(`for="${id}"`);
  });
});

describe("CredentialField", () => {
  const props = {
    label: "Token de Claude Code",
    help: "You generate it with claude setup-token.",
    value: "",
    onChange: () => undefined,
    onSave: () => undefined,
    onRemove: () => undefined,
  };

  it("set: it says so with its last four, allows changing and removing it, without showing the value", () => {
    const html = renderToStaticMarkup(<CredentialField {...props} configured hint="…a3f9" />);

    expect(html).toContain('type="password"');
    expect(html).toContain("…a3f9");
    expect(html).toContain("Remove");
    expect(html).toContain('value=""');
  });

  it("without `onRemove` it can be changed but not removed: a connection does not lose its key", () => {
    const html = renderToStaticMarkup(<CredentialField {...props} onRemove={undefined} configured hint="…a3f9" />);

    expect(html).toContain("…a3f9");
    expect(html).toContain("Save");
    expect(html).not.toContain("Remove");
  });

  it("not set: asks to paste it, says where to get it and does not offer removal", () => {
    const html = renderToStaticMarkup(<CredentialField {...props} configured={false} />);

    expect(html).toContain("Paste it here");
    expect(html).toContain("You generate it with claude setup-token.");
    expect(html).not.toContain("Remove");
  });

  it("what fails is said in the field itself", () => {
    const html = renderToStaticMarkup(
      <CredentialField {...props} configured={false} problem="No se ha guardado." />,
    );

    expect(html).toContain("No se ha guardado.");
    expect(html).toContain('aria-invalid="true"');
  });
});
