import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import * as React from "react";

import { Widget, WidgetDetail, WidgetRow, WidgetRows, WidgetValue } from "../src/index";

const base = { title: "Eventos", hue: 1, size: "2x2", shape: "number" } as const;

const render = (element: React.ReactElement): string => renderToStaticMarkup(element);

describe("la cabecera es del sistema", () => {
  it("se pinta entera aunque no haya datos", () => {
    const html = render(<Widget {...base} state="loading" />);

    expect(html).toContain("Eventos");
    expect(html).toContain('class="widget-dot"');
  });

  it("el tono sale de la paleta fija, no del componente", () => {
    expect(render(<Widget {...base} hue={5} state="ready" />)).toContain('data-hue="5"');
  });
});

describe("los cuatro estados", () => {
  it("loading trae un esqueleto con la forma del contenido, no un spinner", () => {
    const number = render(<Widget {...base} state="loading" />);
    const list = render(<Widget {...base} shape="list" state="loading" />);

    expect(number).toContain("widget-skeleton");
    expect(number.match(/widget-skeleton-bar/g)).toHaveLength(2);
    expect(list.match(/widget-skeleton-bar/g)).toHaveLength(4);
  });

  it("empty dice una frase y no pinta un hueco", () => {
    expect(render(<Widget {...base} state="empty" />)).toContain("Todavía no hay nada");
  });

  it("error CONSERVA el último valor bueno, fechado", () => {
    const html = render(
      <Widget {...base} state="error" updatedAt={new Date(Date.now() - 7200_000)}>
        <WidgetValue>47</WidgetValue>
      </Widget>,
    );

    expect(html).toContain("47");
    expect(html).toContain("hace 2 h");
    expect(html).toContain("No se pudo cargar");
  });

  it("disconnected ofrece conectar, no reintentar", () => {
    const html = render(<Widget {...base} state="disconnected" onConnect={() => {}} />);

    expect(html).toContain("Conectar");
    expect(html).not.toContain("Reintentar");
  });

  it("disconnected dice qué fuente no contesta cuando el módulo lo sabe", () => {
    const html = render(<Widget {...base} state="disconnected" note="Sin conexión con Anthropic" />);

    expect(html).toContain("Sin conexión con Anthropic");
    expect(html).not.toContain("Ningún conector");
  });
});

describe("la duda es un modificador, no un estado", () => {
  const uncertainty = { summary: "puede faltar: 2 eventos en 1 entidad sin unir" };

  it("marca el número con el punteado", () => {
    const html = render(
      <Widget {...base} state="ready" uncertainty={uncertainty}>
        <WidgetValue>7</WidgetValue>
      </Widget>,
    );

    expect(html).toContain('data-uncertain="true"');
  });

  it("sin duda no hay marca", () => {
    const html = render(
      <Widget {...base} state="ready">
        <WidgetValue>7</WidgetValue>
      </Widget>,
    );

    expect(html).not.toContain("data-uncertain");
  });

  it("en 2x2 solo el punteado; la explicación necesita sitio", () => {
    const small = render(
      <Widget {...base} state="ready" uncertainty={uncertainty}>
        <WidgetValue>7</WidgetValue>
      </Widget>,
    );
    const medium = render(
      <Widget {...base} size="4x2" shape="list" state="ready" uncertainty={uncertainty}>
        <WidgetRows>
          <WidgetRow label="Alba Market" value="7 eventos" />
        </WidgetRows>
      </Widget>,
    );

    expect(small).not.toContain(uncertainty.summary);
    expect(medium).toContain(uncertainty.summary);
  });

  it("no se pinta sobre un estado sin dato", () => {
    for (const state of ["empty", "loading"] as const) {
      const html = render(<Widget {...base} state={state} uncertainty={uncertainty} />);
      expect(html).not.toContain(uncertainty.summary);
    }
  });
});

describe("la cabecera", () => {
  it("no lleva raya debajo, tampoco sobre una lista", () => {
    expect(render(<Widget {...base} state="ready" />)).not.toContain("widget-separator");
    expect(render(<Widget {...base} shape="list" state="ready" />)).not.toContain("widget-separator");
  });

  it("lleva el icono de la app cuando la shell lo da, y si no, el punto", () => {
    const conIcono = render(<Widget {...base} state="ready" appIcon="/training/icon.svg" />);
    expect(conIcono).toContain('class="widget-icon"');
    expect(conIcono).toContain('src="/training/icon.svg"');
    expect(conIcono).not.toContain("widget-dot");
    expect(render(<Widget {...base} state="ready" />)).toContain('class="widget-dot"');
  });

  it("pone el tono de la app en la tarjeta, para que lo lea lo de dentro", () => {
    expect(render(<Widget {...base} hue={5} state="ready" />)).toContain('data-hue="5"');
  });
});

describe("el cuerpo", () => {
  it("es lo único que pone el módulo", () => {
    const html = render(
      <Widget {...base} state="ready">
        <WidgetValue>1.284</WidgetValue>
        <WidgetDetail>12 hoy</WidgetDetail>
      </Widget>,
    );

    expect(html).toContain("1.284");
    expect(html).toContain("12 hoy");
    expect(html.match(/widget-header/g)).toHaveLength(1);
  });
});

describe("lo que dice el módulo, se ve", () => {
  it("vacío, con el motivo del módulo y no con la frase genérica", () => {
    const html = render(<Widget {...base} state="empty" note="nada conectado todavía" />);

    expect(html).toContain("nada conectado todavía");
    expect(html).not.toContain("Todavía no hay nada");
  });
});

describe("las listas", () => {
  it("cada fila puede llevar su estado, en punto y en color", () => {
    const html = render(
      <WidgetRows>
        <WidgetRow label="BBVA" value="Caducada" tone="negative" />
        <WidgetRow label="Bitvavo" value="Al día" />
      </WidgetRows>,
    );

    expect(html).toContain('data-tone="negative"');
    expect(html).toContain("widget-row-dot");
    expect(html.match(/widget-row-dot/g)).toHaveLength(1);
  });

  it("se desplaza, y si la tarjeta lleva a algún sitio, tocar una fila lleva allí", () => {
    const linked = render(
      <WidgetRows href="/hub">
        <WidgetRow label="BBVA" value="Caducada" />
      </WidgetRows>,
    );
    const plain = render(
      <WidgetRows>
        <WidgetRow label="BBVA" value="Caducada" />
      </WidgetRows>,
    );

    expect(linked).toMatch(/<a class="widget-rows-scroll" href="\/hub"/);
    expect(plain).toContain('<div class="widget-rows-scroll"');
  });
});

describe("el 1x1", () => {
  it("guarda el título para el lector de pantalla aunque no se vea", () => {
    const html = render(<Widget {...base} size="1x1" state="loading" />);

    expect(html).toContain('data-size="1x1"');
    expect(html).toContain("Eventos");
  });
});
