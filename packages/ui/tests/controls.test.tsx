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
  it("es secundario por defecto y nunca envía un formulario sin pedirlo", () => {
    const html = render(<Button onClick={noop}>Cancelar</Button>);
    expect(html).toContain('data-variant="secondary"');
    expect(html).toContain('type="button"');
  });

  it("lleva la variante, el tamaño y el ancho que se le piden", () => {
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
  it("se anuncia con su etiqueta y el icono queda como decoración", () => {
    const html = render(<IconButton icon="close" label="Cerrar" onClick={noop} />);
    expect(html).toContain('aria-label="Cerrar"');
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

  it("es un grupo de radio con un único elegido", () => {
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-label="Tema"');
    expect(html.match(/role="radio"/g)).toHaveLength(3);
    expect(html.match(/aria-checked="true"/g)).toHaveLength(1);
  });

  it("solo el elegido entra en el orden de tabulación", () => {
    expect(html.match(/tabindex="0"/g)).toHaveLength(1);
    expect(html.match(/tabindex="-1"/g)).toHaveLength(2);
  });

  it("el pulgar sabe cuántos segmentos hay y a cuál ir", () => {
    expect(html).toContain("--segments:3");
    expect(html).toContain("--selected:1");
  });

  it("con un valor que no está en la lista, el pulgar no se va fuera del carril", () => {
    const stray = render(
      <SegmentedControl label="Tema" options={[...options]} value={"sepia" as never} onChange={noop} />,
    );
    expect(stray).toContain("--selected:0");
  });

  it("puede quedarse en solo iconos en pantalla estrecha sin perder el nombre", () => {
    const narrow = render(
      <SegmentedControl label="Tema" options={[...options]} value="light" onChange={noop} iconsWhenNarrow />,
    );
    expect(narrow).toContain("data-icons-narrow");
    expect(narrow).toContain('<span class="segmented-label">Claro</span>');
    expect(html).not.toContain("data-icons-narrow");
  });
});

describe("segmentFor", () => {
  it("las flechas avanzan y dan la vuelta en los extremos", () => {
    expect(segmentFor("ArrowRight", 0, 3)).toBe(1);
    expect(segmentFor("ArrowRight", 2, 3)).toBe(0);
    expect(segmentFor("ArrowLeft", 0, 3)).toBe(2);
    expect(segmentFor("ArrowDown", 1, 3)).toBe(2);
  });

  it("Inicio y Fin van a los extremos y el resto de teclas no mueve nada", () => {
    expect(segmentFor("Home", 2, 3)).toBe(0);
    expect(segmentFor("End", 0, 3)).toBe(2);
    expect(segmentFor("a", 1, 3)).toBeNull();
    expect(segmentFor("ArrowRight", 0, 0)).toBeNull();
  });
});

describe("Slider", () => {
  it("pinta el tramo relleno hasta el valor y anuncia el texto, no el número crudo", () => {
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

  it("el relleno se recorta al carril", () => {
    expect(sliderFill(2, 0, 1)).toBe(100);
    expect(sliderFill(-1, 0, 1)).toBe(0);
    expect(sliderFill(1, 1, 1)).toBe(0);
  });
});

describe("List", () => {
  it("cada fila va en su elemento de lista, y lo deshabilitado sigue en su sitio", () => {
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

  it("con segunda línea y cifra, el nombre y lo que es van apilados y el importe aparte", () => {
    const html = render(
      <ListRow title="Supermercado Alba" subtitle="Sin categoría" value="−60,00 €" tone="warning" onClick={noop} />,
    );
    expect(html).toContain('class="list-row-text"');
    expect(html).toContain('<span class="list-row-subtitle">Sin categoría</span>');
    expect(html).toContain('<span class="list-row-value">−60,00 €</span>');
    expect(html).toContain('data-tone="warning"');
  });

  it("sin segunda línea, la fila es la de siempre", () => {
    const html = render(<ListRow title="Demo" detail="2x2" onClick={noop} />);
    expect(html).not.toContain("list-row-text");
    expect(html).not.toContain("list-row-value");
  });
});

describe("CheckRow", () => {
  it("es una casilla que dice si está marcada, y la fila entera es lo que se toca", () => {
    const html = render(<CheckRow title="Leche" detail="2" checked onToggle={noop} />);
    expect(html).toContain('role="checkbox"');
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("data-checked");
    expect(html).toContain("Leche");
    expect(html).not.toContain("check-row-more");
  });

  it("lo que no es marcar va en su propio botón, y ese botón tiene nombre", () => {
    const html = render(
      <CheckRow title="Pan" checked={false} onToggle={noop} more={{ label: "Cambiar pan", onClick: noop }} />,
    );
    expect(html).toContain('aria-checked="false"');
    expect(html).not.toContain("data-checked");
    expect(html).toContain('aria-label="Cambiar pan"');
  });
});

describe("Stepper", () => {
  it("pequeño, para una fila: lo dice para el CSS y sigue siendo el mismo grupo con su nombre (T-B05)", () => {
    const html = render(<Stepper size="small" label="Reps" value={8} step={1} onChange={noop} />);
    expect(html).toContain('data-size="small"');
    expect(html).toContain('aria-label="Reps"');
    expect(render(<Stepper label="Reps" value={8} step={1} onChange={noop} />)).not.toContain("data-size");
  });

  it("sube y baja por pasos sin arrastrar error de coma flotante", () => {
    let value = 60;
    for (let i = 0; i < 7; i++) value = stepValue(value, 2.5, 1);
    expect(value).toBe(77.5);
    expect(stepValue(0.3, 0.1, 1)).toBe(0.4);
  });

  it("no baja del mínimo ni sube del máximo", () => {
    expect(stepValue(1, 2.5, -1, 0)).toBe(0);
    expect(stepValue(99, 5, 1, 0, 100)).toBe(100);
  });

  it("sin valor, el primer toque arranca en el mínimo en vez de sumar a la nada", () => {
    expect(stepValue(null, 2.5, 1, 20)).toBe(20);
  });

  it("lee la coma de un teclado español, y vacío no es cero", () => {
    expect(parseDecimal("62,5")).toBe(62.5);
    expect(parseDecimal(" 17.5 ")).toBe(17.5);
    expect(parseDecimal("")).toBeNull();
    expect(parseDecimal("abc")).toBeNull();
  });

  it("escribe 60 y 62,5, sin decimales de relleno", () => {
    expect(formatDecimal(60)).toBe("60");
    expect(formatDecimal(62.5)).toBe("62,5");
    expect(formatDecimal(null)).toBe("—");
  });

  it("es un grupo con nombre, y sus botones dicen qué cambian", () => {
    const html = render(<Stepper label="Peso" value={60} step={2.5} unit="kg" onChange={noop} />);
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="Menos peso"');
    expect(html).toContain('aria-label="Más peso"');
    expect(html).not.toContain("<input");
  });

  it("en el mínimo el botón de bajar se apaga", () => {
    const html = render(<Stepper label="Reps" value={0} step={1} onChange={noop} />);
    expect(html).toMatch(/aria-label="Menos reps" disabled/);
  });
});

describe("ChoiceChips", () => {
  it("es un grupo de radio con la elegida marcada", () => {
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
  it("cuenta minutos y segundos, y horas cuando las hay", () => {
    expect(formatElapsed(7_000)).toBe("0:07");
    expect(formatElapsed(750_000)).toBe("12:30");
    expect(formatElapsed(3_902_000)).toBe("1:05:02");
  });

  it("un reloj adelantado no da tiempo negativo", () => {
    expect(formatElapsed(-5_000)).toBe("0:00");
  });

  it("sin fecha de inicio no inventa un cero", () => {
    const html = render(<Elapsed since={null} label="Descanso" now={0} />);
    expect(html).toContain("—");
  });
});

describe("SyncMark y ConfirmButton", () => {
  it("el estado de envío se anuncia, no solo se colorea", () => {
    expect(render(<SyncMark state="pending" />)).toContain('aria-label="Pendiente de enviar"');
    expect(render(<SyncMark state="saved" />)).toContain('aria-label="Guardada"');
  });

  it("confirmar dice si ya está confirmada", () => {
    expect(render(<ConfirmButton label="Confirmar serie 1" confirmed />)).toContain(
      'aria-pressed="true"',
    );
  });
});

describe("AppBar", () => {
  it("acepta acciones y no nodos", () => {
    const html = render(
      <AppBar
        title="Pull"
        subtitle="Rotación 3"
        back={{ icon: "chevron-left", label: "Volver", onClick: noop }}
        action={{ label: "Terminar", onClick: noop }}
      />,
    );
    expect(html).toContain("Pull");
    expect(html).toContain('aria-label="Volver"');
    expect(html).toContain("Terminar");
  });
});

describe("MonthCalendar", () => {
  it("las semanas van de lunes a domingo, con huecos antes del 1", () => {
    const weeks = monthWeeks(2026, 8);
    expect(weeks).toHaveLength(5);
    expect(weeks[0]?.monday).toBe("2026-08-31");
    expect(weeks[0]?.cells[0]).toBeNull();
    expect(weeks[0]?.cells[1]).toEqual({ day: "2026-09-01", date: 1 });
    expect(weeks[4]?.cells.filter(Boolean)).toHaveLength(3);
  });

  it("con etiqueta de semana, cada fila lleva la suya a la izquierda", () => {
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

  it("vacío se pinta entero, con hoy señalado", () => {
    const html = render(
      <MonthCalendar year={2026} month={8} marks={{}} today="2026-09-16" onPrevious={noop} onNext={noop} />,
    );
    expect(html).toContain("Septiembre de 2026");
    expect(html.match(/role="gridcell"/g)).toHaveLength(30);
    expect(html).toMatch(/data-today="true"[^>]*aria-label="miércoles, 16 de septiembre"/);
  });

  it("un día con entreno lleva su tipo y lo dice", () => {
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
    expect(html).toMatch(/data-marked="true" data-kind="pull"[^>]*aria-label="lunes, 14 de septiembre: Pull, 52 min"/);
  });

  it("el día local no se corre por el huso", () => {
    expect(isoDay(new Date(2026, 0, 1, 0, 30))).toBe("2026-01-01");
  });
});

describe("VersionTag", () => {
  it("enseña qué es y qué versión corre, sin adornos", () => {
    const html = render(<VersionTag name="training" version="v1.2.0" />);
    expect(html).toContain("training");
    expect(html).toContain("v1.2.0");
  });
});

describe("TabBar, Sheet y TextField", () => {
  it("la pestaña activa se anuncia como la página actual", () => {
    const html = render(
      <TabBar
        label="Secciones"
        active="plan"
        onSelect={noop}
        items={[
          { id: "hoy", label: "Hoy", icon: "today" },
          { id: "plan", label: "Plan", icon: "edit" },
        ]}
      />,
    );
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-current="page"[^>]*>.*Plan/);
  });

  it("la hoja es un diálogo con nombre y su acción", () => {
    const html = render(
      <Sheet title="Añadir ejercicio" onClose={noop} action={{ label: "Añadir", onClick: noop }}>
        <p>contenido</p>
      </Sheet>,
    );
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-label="Añadir ejercicio"');
    expect(html).toContain("Añadir</span></button>");
  });

  it("sin acción, el cuerpo es lo último y deja sitio a la barra de inicio del teléfono", () => {
    const html = render(
      <Sheet title="¿Empezar Pull?" onClose={noop}>
        <button type="button">Empezar</button>
      </Sheet>,
    );
    expect(html).not.toContain("bottom-sheet-foot");

    const css = readFileSync(new URL("../controls.css", import.meta.url), "utf8");
    const rule = /\.bottom-sheet-body:last-child \{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(rule).toContain("env(safe-area-inset-bottom)");
  });

  it("el campo está unido a su etiqueta y a su pista", () => {
    const html = render(<TextField label="Nombre" value="" onChange={noop} hint="Obligatorio" invalid />);
    const id = /for="([^"]+)"/.exec(html)?.[1];
    expect(html).toContain(`id="${id}"`);
    expect(html).toContain(`aria-describedby="${id}-hint"`);
    expect(html).toContain('aria-invalid="true"');
  });
});

describe("LevelChips", () => {
  const LEVELS = [
    { value: "primary", label: "principal" },
    { value: "secondary", label: "secundario" },
  ] as const;

  it("tocar recorre principal, secundario y sin elegir", () => {
    const levels = [...LEVELS];
    expect(nextLevel(levels, undefined)).toBe("primary");
    expect(nextLevel(levels, "primary")).toBe("secondary");
    expect(nextLevel(levels, "secondary")).toBeUndefined();
  });

  it("el nivel se anuncia y se ve, no solo se colorea", () => {
    const html = render(
      <LevelChips
        label="Músculos"
        levels={[...LEVELS]}
        value={{ chest: "primary", triceps: "secondary" }}
        onChange={noop}
        options={[
          { value: "chest", label: "Pecho" },
          { value: "triceps", label: "Tríceps" },
          { value: "lats", label: "Dorsal" },
        ]}
      />,
    );
    expect(html).toContain('aria-label="Pecho: principal"');
    expect(html).toContain('aria-label="Tríceps: secundario"');
    expect(html).toMatch(/aria-pressed="false" aria-label="Dorsal"/);
    expect(html).toContain("secundario</span>");
  });
});

describe("WallpaperPicker", () => {
  it("marca el elegido, y seguir el heredado es una opción más", () => {
    const options = [
      { id: "marea", name: "Marea", image: "/wallpapers/marea.svg" },
      { id: "duna", name: "Duna", image: "/wallpapers/duna.svg" },
    ];
    const own = render(<WallpaperPicker label="Fondo" options={options} value="duna" onChange={noop} />);
    expect(own.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(own).toMatch(/aria-pressed="true"[^>]*url\(\/wallpapers\/duna.svg\)/);

    const inherited = render(
      <WallpaperPicker
        label="Fondo"
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
  it("es un interruptor con nombre que dice si está encendido", () => {
    const on = render(<Switch label="Programación" checked onChange={noop} />);
    const off = render(<Switch label="Programación" checked={false} onChange={noop} />);

    expect(on).toContain('role="switch"');
    expect(on).toContain('aria-label="Programación"');
    expect(on).toContain('aria-checked="true"');
    expect(off).toContain('aria-checked="false"');
    expect(on).toContain('type="button"');
  });
});

describe("CopyField", () => {
  it("enseña el valor sin dejar editarlo, y el botón copia sin enviar nada", () => {
    const html = renderToStaticMarkup(<CopyField label="ID de cliente" value="claude" />);

    expect(html).toContain('readOnly=""');
    expect(html).toContain('value="claude"');
    expect(html).toContain('type="button"');
    expect(html).toContain('aria-label="Copiar ID de cliente"');
    expect(html).toContain(">Copiar<");
  });

  it("la etiqueta nombra el campo", () => {
    const html = renderToStaticMarkup(<CopyField label="URL del servidor" value="https://x/mcp" />);
    const id = /<input id="([^"]+)"/.exec(html)?.[1];

    expect(id).toBeTruthy();
    expect(html).toContain(`for="${id}"`);
  });
});

describe("CredentialField", () => {
  const props = {
    label: "Token de Claude Code",
    help: "Lo generas con claude setup-token.",
    value: "",
    onChange: () => undefined,
    onSave: () => undefined,
    onRemove: () => undefined,
  };

  it("puesta: lo dice con sus cuatro últimos, deja cambiarla y quitarla, sin enseñar el valor", () => {
    const html = renderToStaticMarkup(<CredentialField {...props} configured hint="…a3f9" />);

    expect(html).toContain('type="password"');
    expect(html).toContain("…a3f9");
    expect(html).toContain("Quitar");
    expect(html).toContain('value=""');
  });

  it("sin `onRemove` se puede cambiar pero no quitar: una conexión no se queda sin su clave", () => {
    const html = renderToStaticMarkup(<CredentialField {...props} onRemove={undefined} configured hint="…a3f9" />);

    expect(html).toContain("…a3f9");
    expect(html).toContain("Guardar");
    expect(html).not.toContain("Quitar");
  });

  it("sin poner: pide pegarla, dice dónde se consigue y no ofrece quitar", () => {
    const html = renderToStaticMarkup(<CredentialField {...props} configured={false} />);

    expect(html).toContain("Pégala aquí");
    expect(html).toContain("Lo generas con claude setup-token.");
    expect(html).not.toContain("Quitar");
  });

  it("lo que falla se dice en el propio campo", () => {
    const html = renderToStaticMarkup(
      <CredentialField {...props} configured={false} problem="No se ha guardado." />,
    );

    expect(html).toContain("No se ha guardado.");
    expect(html).toContain('aria-invalid="true"');
  });
});
