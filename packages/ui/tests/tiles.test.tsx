import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Banner, Photo, PhotoTile, SplitBar, StepItem, StepList, Tile, Tiles } from "../src/index";

describe("la foto y su tarjeta", () => {
  it("sin foto, la placa de su tipo sobre su tono; con ella, la foto", () => {
    const without = renderToStaticMarkup(<Photo hue={3} icon="pin" />);
    expect(without).toContain('class="photo" data-shape="card" data-hue="3"');
    expect(without).toContain("icon-badge");
    const photo = renderToStaticMarkup(<Photo src="/foto.jpg" alt="Un sitio" hue={3} icon="pin" shape="hero" />);
    expect(photo).toContain('src="/foto.jpg"');
    expect(photo).toContain('alt="Un sitio"');
    expect(photo).not.toContain("icon-badge");
  });

  it("con acción es un botón que dice qué hace", () => {
    const html = renderToStaticMarkup(
      <Photo hue={1} icon="pin" shape="banner" action={{ label: "Añadir foto", onClick: () => undefined }} />,
    );
    expect(html).toContain('<button type="button" class="photo" data-shape="banner"');
    expect(html).toContain("Añadir foto");
  });

  it("la tarjeta lleva su etiqueta, su título y su línea, y con enlace es un enlace", () => {
    const html = renderToStaticMarkup(
      <PhotoTile title="Viaje de ejemplo" detail="En mayo" hue={5} icon="plane" badge="Planeando" href="/travel/1" />,
    );
    expect(html).toContain('href="/travel/1"');
    expect(html).toContain("Planeando");
    expect(html).toContain("Viaje de ejemplo");
    expect(html).toContain("En mayo");
  });
});

describe("la tarjeta con portada", () => {
  it("con enlace es un enlace de verdad, con su portada del tono de su grupo", () => {
    const html = renderToStaticMarkup(
      <Tiles label="Recetas">
        <Tile title="Porrusalda" hue={2} figure="15 min" caption="tú delante" detail="Para 4" tags={["olla"]} href="/receta/1" />
      </Tiles>,
    );
    expect(html).toContain('<ul class="tiles" aria-label="Recetas"><li>');
    expect(html).toContain('href="/receta/1"');
    expect(html).toContain('data-hue="2"');
    expect(html).toContain("15 min");
    expect(html).toContain("tú delante");
    expect(html).toContain("olla");
  });

  it("sin enlace es un botón, y sin cifra no pinta su hueco", () => {
    const html = renderToStaticMarkup(<Tile title="Sin cifra" hue={1} onOpen={() => undefined} />);
    expect(html).toContain('<button type="button" class="surface tile"');
    expect(html).not.toContain("tile-figure");
  });
});

describe("el total repartido", () => {
  it("parte la barra en proporción y lo dice a quien no ve los colores", () => {
    const html = renderToStaticMarkup(
      <SplitBar
        label="kcal"
        parts={[
          { label: "Proteína", value: "25 %", share: 1, hue: 1 },
          { label: "Grasa", value: "75 %", share: 3, hue: 3 },
        ]}
      />,
    );
    expect(html).toContain('aria-label="kcal: Proteína 25 %, Grasa 75 %"');
    expect(html).toContain("flex-grow:0.25");
    expect(html).toContain("flex-grow:0.75");
  });

  it("sin nada que repartir no pinta trozos", () => {
    const html = renderToStaticMarkup(<SplitBar label="kcal" parts={[{ label: "Proteína", value: "0 %", share: 0, hue: 1 }]} />);
    expect(html).not.toContain("split-bar-part");
  });
});

describe("la portada de una ficha", () => {
  it("lleva el tono y su dibujo, que no se lee", () => {
    const html = renderToStaticMarkup(<Banner hue={5} glyph={<span>☀</span>}>dentro</Banner>);
    expect(html).toContain('class="surface banner" data-hue="5"');
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("dentro");
  });
});

describe("los pasos", () => {
  it("dice cuál está hecho y cuál toca, con su número o su marca", () => {
    const html = renderToStaticMarkup(
      <StepList label="Pasos">
        <StepItem number={1} text="Picar" done onToggle={() => undefined} />
        <StepItem number={2} text="Cocer" when="min 5 a 35" detail="30 min" done={false} next onToggle={() => undefined} />
        <StepItem number={3} text="Servir" done={false} onToggle={() => undefined} />
      </StepList>,
    );
    expect(html).toContain('aria-label="Pasos"');
    const states = [...html.matchAll(/data-state="([a-z]+)" aria-pressed="(true|false)"/g)].map((found) => `${found[1]}:${found[2]}`);
    expect(states).toEqual(["done:true", "next:false", "todo:false"]);
    expect(html).toContain("min 5 a 35");
    expect(html).toContain(">3<");
  });
});
