import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  Delta,
  DisclosureList,
  DisclosureRow,
  Figures,
  HeadlineFigure,
  Inline,
  ProgressRing,
  Sequence,
  SequenceRow,
  Stack,
  WeekDots,
} from "../src/index";

const render = (element: React.ReactElement) => renderToStaticMarkup(element);
const noop = () => {};

describe("las cifras", () => {
  it("un cambio dice su dirección, y con nombre se lee entero", () => {
    expect(render(<Delta text="+2,5 kg" direction="up" />)).toBe('<span class="delta" data-direction="up">+2,5 kg</span>');
    expect(render(<Delta text="+2,5 kg" direction="up" label="Mejor serie: +2,5 kg" />)).toContain(
      'aria-label="Mejor serie: +2,5 kg"',
    );
  });

  it("las cifras en fila, con su nombre y lo que merece fijarse marcado", () => {
    const html = render(
      <Figures
        items={[
          { label: "minutos", value: 75 },
          { label: "récords", value: 2, lit: true },
        ]}
      />,
    );
    expect(html).toContain("<dt>minutos</dt><dd>75</dd>");
    expect(html).toContain('<div data-lit=""><dt>récords</dt><dd>2</dd>');
    expect(render(<Figures items={[{ label: "11+ reps", value: "80 kg", muted: true }]} />)).toContain('data-muted=""');
  });

  it("la cifra destacada lleva su unidad y lo que cambió", () => {
    const html = render(
      <HeadlineFigure label="Máximo estimado" value={119} unit="kg" change={{ text: "+6 kg", direction: "up" }} />,
    );
    expect(html).toContain("Máximo estimado");
    expect(html).toContain('class="headline-figure-unit"> kg');
    expect(html).toContain('data-direction="up">+6 kg');
  });

  it("el anillo cuenta hasta completarse, y completo lleva su ✓", () => {
    expect(render(<ProgressRing done={2} target={4} />)).toContain('stroke-dasharray="50 100"');
    expect(render(<ProgressRing done={2} target={4} />)).toContain(">2</span>");
    expect(render(<ProgressRing done={4} target={4} />)).toContain('data-complete="true"');
    expect(render(<ProgressRing done={4} target={4} />)).toContain(">✓</span>");
  });
});

describe("las filas", () => {
  it("una fila plegada no enseña su cuerpo; abierta, sí, con su etiqueta", () => {
    const closed = render(
      <DisclosureList label="Ejercicios">
        <DisclosureRow title="Sentadilla" subtitle="3 × 6–10" open={false} onToggle={noop}>
          <p>Series</p>
        </DisclosureRow>
      </DisclosureList>,
    );
    expect(closed).toContain('aria-expanded="false"');
    expect(closed).not.toContain("<p>Series</p>");

    const open = render(
      <DisclosureRow title="Sentadilla" tag="superserie" open onToggle={noop}>
        <p>Series</p>
      </DisclosureRow>,
    );
    expect(open).toContain('aria-expanded="true"');
    expect(open).toContain("<p>Series</p>");
    expect(open).toContain('class="disclosure-tag"> · superserie');
  });

  it("los pasos dicen su estado, y uno hecho se toca para corregirlo", () => {
    const html = render(
      <Sequence>
        <li>
          <SequenceRow number={1} state="done" value="8 × 60 kg" onClick={noop} label="Serie 1" />
        </li>
        <li>
          <SequenceRow number={2} state="todo" value="8 × 60 kg" />
        </li>
      </Sequence>,
    );
    expect(html).toMatch(/<button type="button" class="sequence-row" data-state="done" aria-label="Serie 1">/);
    expect(html).toMatch(/<div class="sequence-row" data-state="todo">/);
  });

  it("colocar no necesita CSS de la app", () => {
    expect(render(<Stack gap="section">a</Stack>)).toBe('<div class="stack" data-gap="section">a</div>');
    expect(render(<Inline label="Actividades">a</Inline>)).toContain('role="group"');
  });
});

describe("la semana, grande y por tipo", () => {
  it("cada día cumplido lleva el color de lo que se hizo y su ✓; hoy, su anillo", () => {
    const html = render(
      <WeekDots
        size="large"
        label="2 de 4"
        days={[
          { day: "2026-09-14", state: "met", kind: "push" },
          { day: "2026-09-15", state: "met", kind: "pull", today: true },
        ]}
      />,
    );
    expect(html).toContain('data-size="large"');
    expect(html).toMatch(/data-state="met" data-kind="pull" data-today="true"/);
    expect(html).toContain(">✓</span>");
  });
});
