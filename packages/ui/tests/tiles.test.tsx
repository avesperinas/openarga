import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Banner, Photo, PhotoTile, SplitBar, StepItem, StepList, Tile, Tiles } from "../src/index";

describe("the photo and its card", () => {
  it("without a photo, its kind's badge on its tone; with one, the photo", () => {
    const without = renderToStaticMarkup(<Photo hue={3} icon="pin" />);
    expect(without).toContain('class="photo" data-shape="card" data-hue="3"');
    expect(without).toContain("icon-badge");
    const photo = renderToStaticMarkup(<Photo src="/foto.jpg" alt="Un sitio" hue={3} icon="pin" shape="hero" />);
    expect(photo).toContain('src="/foto.jpg"');
    expect(photo).toContain('alt="Un sitio"');
    expect(photo).not.toContain("icon-badge");
  });

  it("with an action it is a button that says what it does", () => {
    const html = renderToStaticMarkup(
      <Photo hue={1} icon="pin" shape="banner" action={{ label: "Add photo", onClick: () => undefined }} />,
    );
    expect(html).toContain('<button type="button" class="photo" data-shape="banner"');
    expect(html).toContain("Add photo");
  });

  it("the card carries its label, title and line, and with a link it is a link", () => {
    const html = renderToStaticMarkup(
      <PhotoTile title="Viaje de ejemplo" detail="En mayo" hue={5} icon="plane" badge="Planeando" href="/travel/1" />,
    );
    expect(html).toContain('href="/travel/1"');
    expect(html).toContain("Planeando");
    expect(html).toContain("Viaje de ejemplo");
    expect(html).toContain("En mayo");
  });
});

describe("the card with a cover", () => {
  it("with a link it is a real link, with a cover in its group's tone", () => {
    const html = renderToStaticMarkup(
      <Tiles label="Recetas">
        <Tile title="Leek soup" hue={2} figure="15 min" caption="you in front" detail="Serves 4" tags={["pot"]} href="/receta/1" />
      </Tiles>,
    );
    expect(html).toContain('<ul class="tiles" aria-label="Recetas"><li>');
    expect(html).toContain('href="/receta/1"');
    expect(html).toContain('data-hue="2"');
    expect(html).toContain("15 min");
    expect(html).toContain("you in front");
    expect(html).toContain("pot");
  });

  it("without a link it is a button, and without a figure it draws no gap", () => {
    const html = renderToStaticMarkup(<Tile title="No figure" hue={1} onOpen={() => undefined} />);
    expect(html).toContain('<button type="button" class="surface tile"');
    expect(html).not.toContain("tile-figure");
  });
});

describe("the total broken down", () => {
  it("splits the bar in proportion and tells whoever cannot see the colours", () => {
    const html = renderToStaticMarkup(
      <SplitBar
        label="kcal"
        parts={[
          { label: "Protein", value: "25 %", share: 1, hue: 1 },
          { label: "Fat", value: "75 %", share: 3, hue: 3 },
        ]}
      />,
    );
    expect(html).toContain('aria-label="kcal: Protein 25 %, Fat 75 %"');
    expect(html).toContain("flex-grow:0.25");
    expect(html).toContain("flex-grow:0.75");
  });

  it("with nothing to split it draws no slices", () => {
    const html = renderToStaticMarkup(<SplitBar label="kcal" parts={[{ label: "Protein", value: "0 %", share: 0, hue: 1 }]} />);
    expect(html).not.toContain("split-bar-part");
  });
});

describe("a record's cover", () => {
  it("carries the tone and its drawing, which is not read", () => {
    const html = renderToStaticMarkup(<Banner hue={5} glyph={<span>☀</span>}>dentro</Banner>);
    expect(html).toContain('class="surface banner" data-hue="5"');
    expect(html).toContain('aria-hidden="true"');
    expect(html).toContain("dentro");
  });
});

describe("the steps", () => {
  it("says which is done and which is due, with its number or mark", () => {
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
