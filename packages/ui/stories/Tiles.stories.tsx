import type { Meta, StoryObj } from "@storybook/react";

import * as React from "react";

import { Banner, Figures, Icon, Photo, PhotoTile, SplitBar, StepItem, StepList, Tile, Tiles } from "../src/index";

const meta: Meta = { title: "Piezas/Portadas y repartos" };
export default meta;

export const Recetario: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 400 }}>
      <Tiles label="Recetas">
        <Tile
          title="Porrusalda de ejemplo"
          hue={2}
          figure="15 min"
          caption="tú delante"
          glyph={<Icon name="flame" />}
          detail="Para 4 · 55 min"
          tags={["invierno", "olla"]}
          onOpen={() => undefined}
        />
        <Tile title="Tostada sintética" hue={3} figure="5 min" caption="en total" glyph={<Icon name="sun" />} detail="Para 1" tags={["desayuno"]} onOpen={() => undefined} />
        <Tile title="Guiso largo de prueba con un nombre que no cabe en dos líneas" hue={6} figure="sin faena" caption="2 h en total" detail="Para 8" onOpen={() => undefined} />
        <Tile title="Cena de ejemplo" hue={5} figure="20 min" caption="en total" glyph={<Icon name="moon" />} detail="Para 2" tags={["cena"]} onOpen={() => undefined} />
      </Tiles>
    </div>
  ),
};

export const Reparto: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 360 }}>
      <SplitBar
        label="De dónde salen las kcal"
        parts={[
          { label: "Proteína", value: "17 %", share: 130, hue: 1 },
          { label: "Grasa", value: "45 %", share: 355, hue: 3 },
          { label: "Hidratos", value: "38 %", share: 298, hue: 2 },
        ]}
      />
    </div>
  ),
};

export const Portada: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 400 }}>
      <Banner hue={2} glyph={<Icon name="flame" />}>
        <Figures
          items={[
            { label: "De principio a fin", value: "55 min" },
            { label: "Tú delante", value: "15 min", lit: true },
          ]}
        />
      </Banner>
    </div>
  ),
};

function Cooking() {
  const steps = ["Picar el puerro de ejemplo.", "Rehogar a fuego medio hasta que esté blando.", "Cocer con agua y patata."];
  const [done, setDone] = React.useState<number[]>([1]);
  const next = steps.findIndex((_, index) => !done.includes(index + 1)) + 1;
  return (
    <StepList label="Pasos">
      {steps.map((text, index) => (
        <StepItem
          key={text}
          number={index + 1}
          text={text}
          when={`min ${index * 10} a ${index * 10 + 10}`}
          detail="10 min"
          done={done.includes(index + 1)}
          next={next === index + 1}
          onToggle={() => setDone((now) => (now.includes(index + 1) ? now.filter((one) => one !== index + 1) : [...now, index + 1]))}
        />
      ))}
    </StepList>
  );
}

export const Pasos: StoryObj = { render: () => <div style={{ maxWidth: 400 }}><Cooking /></div> };

export const Fotos: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 400, display: "grid", gap: 16 }}>
      <Tiles label="Escapadas">
        <PhotoTile title="Mirador de ejemplo" detail="Navarra · escapada" hue={3} icon="mountain" onOpen={() => undefined} />
        <PhotoTile title="Viaje inventado" detail="En mayo" hue={5} icon="plane" badge="Planeando" href="#" />
      </Tiles>
      <Photo hue={2} icon="food" shape="hero" />
      <Photo hue={1} icon="camera" shape="banner" action={{ label: "Añadir foto", onClick: () => undefined }} />
    </div>
  ),
};
