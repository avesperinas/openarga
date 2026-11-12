import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  Columns,
  Cover,
  CoverWall,
  DayTimeline,
  DayTimelines,
  DockBar,
  FrequencyBar,
  FrequencyRow,
  FrequencyRows,
  MediaCard,
  MediaHero,
  RingFigure,
} from "../src/index";

const render = (element: React.ReactElement) => renderToStaticMarkup(element);
const noop = () => {};

describe("el anillo con su cifra", () => {
  it("llena su parte, con la cifra dentro y su nombre y su línea", () => {
    const html = render(<RingFigure share={0.42} value="42 %" label="Ventana" detail="acaba a las 18:30" />);
    expect(html).toContain('stroke-dasharray="42 100"');
    expect(html).toContain('<span class="share-ring-value">42 %</span>');
    expect(html).toContain("Ventana");
    expect(html).toContain("acaba a las 18:30");
  });

  it("sin dato, el anillo vacío; y lo que pasa de uno se queda en lleno", () => {
    expect(render(<RingFigure share={null} value="–" label="Semana" />)).not.toContain("share-ring-fill");
    expect(render(<RingFigure share={1.4} value="140 %" label="Semana" />)).toContain('stroke-dasharray="100 100"');
    expect(render(<RingFigure share={0.7} value="70 %" label="Semana" tone="warning" size="medium" />)).toContain(
      'data-size="medium" data-tone="warning"',
    );
  });

  it("el anillo toma el color de cómo va: de sobra, a ritmo, ojo o al límite", () => {
    for (const tone of ["positive", "info", "warning", "negative"] as const) {
      expect(render(<RingFigure share={0.5} value="50 %" label="Semana" tone={tone} />)).toContain(`data-tone="${tone}"`);
    }
  });
});

describe("cada cuánto", () => {
  it("hasta la marca es lo normal", () => {
    const html = render(<FrequencyBar since={7} every={14} label="cada 2 semanas, hace 7 días" />);
    expect(html).toContain('aria-label="cada 2 semanas, hace 7 días"');
    expect(html).toContain("width:50%");
    expect(html).toContain("left:100%");
    expect(html).not.toContain("data-over");
  });

  it("pasada la marca, se dice, y la marca queda donde tocaba", () => {
    const html = render(<FrequencyBar since={16} every={8} label="cada 8 días, hace 16" />);
    expect(html).toContain('data-over="true"');
    expect(html).toContain("width:100%");
    expect(html).toContain("left:50%");
  });

  it("en su fila, con su nombre y su cifra, y tocarla la abre", () => {
    const html = render(
      <FrequencyRows label="Lo que compras">
        <FrequencyRow title="Tomate" since={15} every={8} label="cada 8 días, hace 15" value="15 / 8 d" onClick={noop} />
      </FrequencyRows>,
    );
    expect(html).toContain('aria-label="Lo que compras"');
    expect(html).toContain('<button type="button" class="frequency-row">');
    expect(html).toContain('class="frequency-row-value" data-over="true">15 / 8 d');
  });

  it("sin costumbre todavía, la barra sin marca", () => {
    expect(render(<FrequencyBar since={3} every={null} label="hace 3 días" />)).not.toContain("frequency-bar-mark");
  });
});

describe("el día en 24 horas", () => {
  it("pone cada marca y cada tramo a su hora, y ahora en rojo", () => {
    const html = render(<DayTimeline label="Hoy" marks={[6]} spans={[{ from: 6, to: 11 }]} now={12} name="J" state="today" />);
    expect(html).toContain('class="day-timeline-mark" style="left:25%"');
    expect(html).toContain("left:25%;width:calc(45.83333333333333% - 25%)");
    expect(html).toContain('class="day-timeline-now" style="left:50%"');
    expect(html).toContain('data-state="today"');
    expect(html).toContain(">J</span>");
  });

  it("discreta, lo marca para pintarse en gris; sin pedirlo, no", () => {
    expect(render(<DayTimeline label="Hoy" spans={[{ from: 6, to: 11 }]} quiet />)).toContain('data-quiet="true"');
    expect(render(<DayTimeline label="Hoy" spans={[{ from: 6, to: 11 }]} />)).not.toContain("data-quiet");
  });

  it("un tramo que pasa de medianoche se corta en las 24", () => {
    expect(render(<DayTimeline label="Hoy" spans={[{ from: 22, to: 27 }]} />)).toContain("calc(100% - 91.66666666666666%)");
  });

  it("con algo que hacer al tocarlo es un botón, y las horas van al pie", () => {
    const html = render(
      <DayTimelines>
        <DayTimeline label="Lunes" name="L" onClick={noop} />
      </DayTimelines>,
    );
    expect(html).toContain('<button type="button" class="day-timeline"');
    expect(html).toContain('<span class="day-timeline-hours"><span>0</span><span>6</span>');
  });
});

describe("barra de abajo y portadas", () => {
  it("la barra de abajo lleva su texto y su acción", () => {
    const html = render(<DockBar title="4 en el carro" detail="Pan y 3 más" action={{ label: "Terminar", onClick: noop }} />);
    expect(html).toContain('aria-label="4 en el carro"');
    expect(html).toContain("Pan y 3 más");
    expect(html).toContain(">Terminar</button>");
  });

  it("una portada sin imagen es su título; el muro las abre por su id", () => {
    expect(render(<Cover title="Un libro" subtitle="Alguien" />)).toContain('<span class="cover-title">Un libro</span>');
    expect(render(<Cover title="Un libro" src="/x.jpg" />)).toContain('alt="Portada de Un libro"');
    const wall = render(<CoverWall items={[{ id: "b1", title: "Uno", note: "★★★", muted: true }]} onOpen={noop} />);
    expect(wall).toContain('aria-label="Uno"');
    expect(wall).toContain('data-muted="true"');
    expect(wall).toContain("★★★");
  });
});

describe("colocar y destacar", () => {
  it("las columnas dicen cuántas son", () => {
    expect(render(<Columns count={3}><span>a</span></Columns>)).toBe('<div class="columns" data-count="3"><span>a</span></div>');
  });

  it("la tarjeta de lo que tienes entre manos se abre al tocarla y lleva su acción aparte", () => {
    const html = render(
      <MediaCard
        media={<Cover title="Un libro" />}
        title="Un libro"
        lines={["Alguien", "Desde el 1 oct"]}
        onOpen={noop}
        action={{ label: "Terminado hoy", icon: "done", onClick: noop }}
      />,
    );
    expect(html).toContain('<button type="button" class="media-card-open">');
    expect(html).toContain('class="media-card-line" data-first="true">Alguien');
    expect(html).toContain("Terminado hoy");
  });

  it("la imagen grande va centrada con lo suyo debajo", () => {
    const html = render(<MediaHero media={<Cover title="Un libro" size="hero" />}><p>Alguien</p></MediaHero>);
    expect(html).toContain('<section class="media-hero">');
    expect(html).toContain('<div class="media-hero-text"><p>Alguien</p></div>');
  });
});

