import type { Meta, StoryObj } from "@storybook/react";

import * as React from "react";

import { Banner, Figures, Icon, Photo, PhotoTile, SplitBar, StepItem, StepList, Tile, Tiles } from "../src/index";

const meta: Meta = { title: "Pieces/Covers and splits" };
export default meta;

export const Recetario: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 400 }}>
      <Tiles label="Recetas">
        <Tile
          title="Sample leek soup"
          hue={2}
          figure="15 min"
          caption="you in front"
          glyph={<Icon name="flame" />}
          detail="Serves 4 · 55 min"
          tags={["invierno", "olla"]}
          onOpen={() => undefined}
        />
        <Tile title="Synthetic toast" hue={3} figure="5 min" caption="in total" glyph={<Icon name="sun" />} detail="Serves 1" tags={["desayuno"]} onOpen={() => undefined} />
        <Tile title="Long test stew with a name that does not fit on two lines" hue={6} figure="no work" caption="2 h in total" detail="Serves 8" onOpen={() => undefined} />
        <Tile title="Sample dinner" hue={5} figure="20 min" caption="in total" glyph={<Icon name="moon" />} detail="Serves 2" tags={["cena"]} onOpen={() => undefined} />
      </Tiles>
    </div>
  ),
};

export const Reparto: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 360 }}>
      <SplitBar
        label="Where the kcal come from"
        parts={[
          { label: "Protein", value: "17 %", share: 130, hue: 1 },
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
            { label: "From start to end", value: "55 min" },
            { label: "You in front", value: "15 min", lit: true },
          ]}
        />
      </Banner>
    </div>
  ),
};

function Cooking() {
  const steps = ["Chop the sample leek.", "Fry gently over medium heat until soft.", "Cook with water and potato."];
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
        <PhotoTile title="Sample viewpoint" detail="Navarra · getaway" hue={3} icon="mountain" onOpen={() => undefined} />
        <PhotoTile title="Viaje inventado" detail="In May" hue={5} icon="plane" badge="Planeando" href="#" />
      </Tiles>
      <Photo hue={2} icon="food" shape="hero" />
      <Photo hue={1} icon="camera" shape="banner" action={{ label: "Add photo", onClick: () => undefined }} />
    </div>
  ),
};
