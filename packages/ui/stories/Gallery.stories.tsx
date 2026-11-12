/// <reference types="vite/client" />
import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import {
  type Hue,
  WALLPAPERS,
  Widget,
  WidgetBars,
  WidgetCalendar,
  WidgetChart,
  WidgetFootnote,
  WidgetHeatmap,
  WidgetKpi,
  WidgetKpiDelta,
  WidgetProgress,
  WidgetRing,
  WidgetRow,
  WidgetRows,
  WidgetStats,
  WidgetUpNext,
  type WidgetShape,
  type WidgetSize,
  spanOf,
  wallpaperStyle,
} from "../src/index";
import "../library.css";
import "../widget.css";

import arcaIcon from "../../../modules/arca/ui/public/icon.svg?url";
import recipesIcon from "../../../modules/recipes/ui/public/icon.svg?url";
import studyIcon from "../../../modules/study/ui/public/icon.svg?url";
import chupingIcon from "../../../modules/chuping/ui/public/icon.svg?url";
import moneyIcon from "../../../modules/money/ui/public/icon.svg?url";
import hubIcon from "../../../modules/hub/ui/public/icon.svg?url";
import plannerIcon from "../../../modules/planner/ui/public/icon.svg?url";
import travelIcon from "../../../modules/travel/ui/public/icon.svg?url";
import libraryIcon from "../../../modules/library/ui/public/icon.svg?url";
import shoppingIcon from "../../../modules/shopping/ui/public/icon.svg?url";
import vitalsIcon from "../../../modules/vitals/ui/public/icon.svg?url";
import trainingIcon from "../../../modules/training/ui/public/icon.svg?url";

const meta = {
  title: "Galería",
  parameters: { layout: "fullscreen" },
  excludeStories: ["APPS"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

interface App {
  name: string;
  hue: Hue;
  icon: string;
}

const APPS = {
  arca: { name: "Arca", hue: 6, icon: arcaIcon },
  recipes: { name: "Recipes", hue: 7, icon: recipesIcon },
  study: { name: "Study", hue: 6, icon: studyIcon },
  chuping: { name: "Chuping", hue: 3, icon: chupingIcon },
  money: { name: "Money", hue: 2, icon: moneyIcon },
  hub: { name: "Hub", hue: 6, icon: hubIcon },
  planner: { name: "Planner", hue: 6, icon: plannerIcon },
  travel: { name: "Travel", hue: 8, icon: travelIcon },
  library: { name: "Library", hue: 5, icon: libraryIcon },
  shopping: { name: "Shopping", hue: 1, icon: shoppingIcon },
  vitals: { name: "Vitals", hue: 5, icon: vitalsIcon },
  training: { name: "Training", hue: 4, icon: trainingIcon },
} satisfies Record<string, App>;

interface Card {
  app: App;
  title: string;
  shape: WidgetShape;
  sizes: WidgetSize[];
  body: () => React.ReactNode;
  state?: "empty";
  note?: string;
}

const inHours = (hours: number) => new Date(Date.now() + hours * 3_600_000);

const CARDS: Card[] = [
  {
    app: APPS.training,
    title: "Entreno",
    shape: "number",
    sizes: ["2x2", "1x1"],
    body: () => <WidgetRing value={3} target={4} label="de 4 esta semana" />,
  },
  {
    app: APPS.training,
    title: "Siguiente sesión",
    shape: "number",
    sizes: ["2x2"],
    body: () => <WidgetKpi value="Pierna" icon="leg" hue={1} detail="Rotación 12" />,
  },
  {
    app: APPS.vitals,
    title: "Pasos hoy",
    shape: "number",
    sizes: ["2x2", "1x1"],
    body: () => <WidgetRing value={6480} target={8000} label="de 8.000" />,
  },
  {
    app: APPS.vitals,
    title: "Peso",
    shape: "number",
    sizes: ["2x2", "1x1"],
    body: () => (
      <WidgetKpiDelta value={74.2} previous={75.1} unit="kg" since="hace 30 días" goodWhen="down" />
    ),
  },
  {
    app: APPS.vitals,
    title: "Colesterol LDL",
    shape: "number",
    sizes: ["2x2", "1x1"],
    body: () => (
      <WidgetKpiDelta value={112} previous={128} unit="mg/dL" since="análisis anterior" goodWhen="down" />
    ),
  },
  {
    app: APPS.vitals,
    title: "Pasos del año",
    shape: "number",
    sizes: ["4x2", "2x2"],
    body: () => (
      <WidgetHeatmap
        values={Array.from({ length: 140 }, (_, i) => ((i * 37) % 11) / 10)}
        columns={20}
        detail="Media de 7.412 al día"
      />
    ),
  },
  {
    app: APPS.money,
    title: "Patrimonio",
    shape: "number",
    sizes: ["4x2", "2x2"],
    body: () => (
      <WidgetKpiDelta value={48210} previous={46890} unit="€" since="el mes pasado" goodWhen="up" />
    ),
  },
  {
    app: APPS.money,
    title: "Bancos",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => (
      <>
        <WidgetStats
          items={[
            { label: "Bancos", value: 2 },
            { label: "Cuentas", value: 5 },
            { label: "Última sincronización", value: "2 h" },
          ]}
        />
        <WidgetFootnote>El acceso a Banco Norte caduca en 5 días.</WidgetFootnote>
      </>
    ),
  },
  {
    app: APPS.money,
    title: "Flujo",
    shape: "number",
    sizes: ["4x2", "2x2"],
    body: () => (
      <WidgetBars
        series={[820, 1240, -310, 460, 990, 610]}
        labels={["abr", "may", "jun", "jul", "ago", "sep"]}
        value="+610"
        unit="€"
        detail="Lo que te queda este mes"
        highlight={5}
      />
    ),
  },
  {
    app: APPS.money,
    title: "En qué gastas",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetRows>
        <WidgetRow label="Supermercado" value="412 €" />
        <WidgetRow label="Restaurantes" value="186 €" />
        <WidgetRow label="Transporte" value="94 €" />
        <WidgetRow label="Suscripciones" value="41 €" />
        <WidgetRow label="Hogar" value="38 €" />
      </WidgetRows>
    ),
  },
  {
    app: APPS.money,
    title: "Cartera",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetKpiDelta value={12840} previous={12310} unit="€" since="hace 30 días" goodWhen="up" />
    ),
  },
  {
    app: APPS.money,
    title: "Lo común",
    shape: "number",
    sizes: ["2x2"],
    body: () => <WidgetKpi value="−23,40" unit="€" detail="Debes a Casa" />,
  },
  {
    app: APPS.money,
    title: "Ahorro del mes",
    shape: "number",
    sizes: ["2x2"],
    body: () => <WidgetRing value={22} target={100} unit="%" label="de lo que entra" show="percent" />,
  },
  {
    app: APPS.money,
    title: "Lo que viene",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetUpNext
        events={[
          { at: inHours(20), title: "Alquiler", detail: "−650 €" },
          { at: inHours(70), title: "Luz", detail: "−48 €" },
          { at: inHours(140), title: "Gimnasio", detail: "−35 €" },
        ]}
      />
    ),
  },
  {
    app: APPS.money,
    title: "Tendencia del gasto",
    shape: "number",
    sizes: ["4x2", "2x2"],
    body: () => (
      <WidgetChart
        series={[1320, 1410, 1280, 1500, 1390, 1210, 1290, 1180]}
        value="1.180"
        unit="€"
        detail="Gasto medio de los últimos 3 meses"
      />
    ),
  },
  {
    app: APPS.money,
    title: "Colchón",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => <WidgetProgress value={7400} target={9000} unit="€" label="de 6 meses de gastos" />,
  },
  {
    app: APPS.planner,
    title: "Próximo",
    shape: "list",
    sizes: ["2x2", "2x4", "4x2"],
    body: () => (
      <WidgetUpNext
        events={[
          { at: inHours(1.5), title: "Dentista", detail: "Clínica Sur" },
          { at: inHours(5), title: "Cena con Irati" },
          { at: inHours(26), title: "Revisión del coche", detail: "Taller" },
        ]}
      />
    ),
  },
  {
    app: APPS.planner,
    title: "Este mes",
    shape: "number",
    sizes: ["2x2"],
    body: () => <WidgetCalendar marked={[2, 5, 9, 14, 21, 28, 30]} today={28} />,
  },
  {
    app: APPS.study,
    title: "Próximo en Study",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetUpNext
        events={[
          { at: inHours(16), title: "Estadística II", detail: "Study 2.04" },
          { at: inHours(40), title: "Entrega práctica 3", detail: "Bases de datos" },
        ]}
      />
    ),
  },
  {
    app: APPS.study,
    title: "Progreso",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => <WidgetProgress value={132} target={240} unit="ECTS" label="del grado" />,
  },
  {
    app: APPS.study,
    title: "Media",
    shape: "number",
    sizes: ["2x2"],
    body: () => <WidgetKpi value="7,8" detail="Ponderada por créditos" />,
  },
  {
    app: APPS.arca,
    title: "Próximo en Arca",
    shape: "list",
    sizes: ["2x2", "2x4", "4x2"],
    body: () => (
      <WidgetRows>
        <WidgetRow label="ITV del coche" value="en 12 días" tone="warning" />
        <WidgetRow label="Revisión caldera" value="en 30 días" tone="neutral" />
        <WidgetRow label="Seguro hogar" value="en 2 meses" tone="neutral" />
        <WidgetRow label="Pasaporte" value="en 7 meses" tone="neutral" />
      </WidgetRows>
    ),
  },
  {
    app: APPS.arca,
    title: "Vencido",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetRows>
        <WidgetRow label="Filtro del agua" value="hace 3 días" tone="negative" />
      </WidgetRows>
    ),
  },
  {
    app: APPS.recipes,
    title: "Recetario",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetStats
        items={[
          { label: "Recetas", value: 48 },
          { label: "Categorías", value: 9 },
        ]}
      />
    ),
  },
  {
    app: APPS.recipes,
    title: "En media hora",
    shape: "list",
    sizes: ["2x2", "2x4", "4x2"],
    body: () => (
      <WidgetRows>
        <WidgetRow label="Tortilla de patatas" value="25 min" />
        <WidgetRow label="Crema de calabaza" value="30 min" />
        <WidgetRow label="Salteado de gambas" value="15 min" />
      </WidgetRows>
    ),
  },
  {
    app: APPS.chuping,
    title: "Ventana de Claude",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <>
        <WidgetRows>
          <WidgetRow label="Se abre" value="08:30" tone="positive" />
          <WidgetRow label="Se renueva" value="13:30" />
          <WidgetRow label="Usado" value="42 %" />
        </WidgetRows>
        <WidgetFootnote>Próximo ping mañana a las 08:30</WidgetFootnote>
      </>
    ),
  },
  {
    app: APPS.hub,
    title: "Hub",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <>
        <WidgetRows>
          <WidgetRow label="Banco Norte" value="Caducada" tone="negative" />
          <WidgetRow label="Caja Sur" value="A medias" tone="warning" />
          <WidgetRow label="Exchange" value="Al día" tone="positive" />
          <WidgetRow label="Correo" value="Al día" tone="positive" />
          <WidgetRow label="Claude" value="En pausa" tone="neutral" />
        </WidgetRows>
        <WidgetFootnote>El acceso a Banco Norte caducó; hay que reconectarlo.</WidgetFootnote>
      </>
    ),
  },
  {
    app: APPS.travel,
    title: "Países",
    shape: "number",
    sizes: ["2x2", "1x1"],
    body: () => <WidgetKpi value={23} detail="4 este año" />,
  },
  {
    app: APPS.travel,
    title: "Último viaje",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetUpNext events={[{ at: inHours(-24 * 20), title: "Lisboa", detail: "4 noches" }]} />
    ),
  },
  {
    app: APPS.travel,
    title: "Viajes por año",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetBars
        series={[3, 5, 2, 6, 4]}
        labels={["2022", "2023", "2024", "2025", "2026"]}
        value={4}
        detail="viajes este año"
        highlight={4}
      />
    ),
  },
  {
    app: APPS.library,
    title: "Leyendo",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetRows>
        <WidgetRow label="La montaña mágica" value="38 %" />
        <WidgetRow label="Patria" value="71 %" />
      </WidgetRows>
    ),
  },
  {
    app: APPS.library,
    title: "Objetivo del año",
    shape: "number",
    sizes: ["2x2"],
    body: () => <WidgetRing value={14} target={20} label="libros de 20" />,
  },
  {
    app: APPS.library,
    title: "Páginas por mes",
    shape: "number",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetBars
        series={[320, 410, 280, 520, 190, 460, 380, 300, 440]}
        labels={["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep"]}
        value={440}
        detail="páginas en septiembre"
        highlight={8}
      />
    ),
  },
  {
    app: APPS.shopping,
    title: "La compra",
    shape: "list",
    sizes: ["2x2", "2x4", "4x2"],
    body: () => (
      <>
        <WidgetRows>
          <WidgetRow label="Leche" value="2" />
          <WidgetRow label="Tomates" value="1 kg" />
          <WidgetRow label="Pan" value="1" />
          <WidgetRow label="Huevos" value="12" />
          <WidgetRow label="Café" value="1" />
        </WidgetRows>
        <WidgetFootnote>5 cosas en la lista</WidgetFootnote>
      </>
    ),
  },
  {
    app: APPS.shopping,
    title: "Te toca",
    shape: "list",
    sizes: ["2x2", "4x2"],
    body: () => (
      <WidgetRows>
        <WidgetRow label="Detergente" value="hace 5 semanas" tone="warning" />
        <WidgetRow label="Aceite" value="hace 6 semanas" tone="warning" />
      </WidgetRows>
    ),
  },
  {
    app: APPS.training,
    title: "Entreno",
    shape: "number",
    sizes: ["1x1"],
    body: () => <WidgetRing value={4} target={4} />,
  },
  {
    app: APPS.library,
    title: "Leyendo",
    shape: "list",
    sizes: ["2x2"],
    state: "empty",
    note: "no estás leyendo nada ahora",
    body: () => null,
  },
];

function Grid({ columns, children }: { columns: number; children: React.ReactNode }) {
  return (
    <div
      data-wallpaper="desktop"
      style={{
        ...wallpaperStyle(WALLPAPERS[0]!),
        position: "relative",
        display: "grid",
        gridTemplateColumns: `repeat(${columns}, 84px)`,
        gridAutoRows: "84px",
        gridAutoFlow: "dense",
        gap: "var(--grid-gap)",
        padding: "var(--space-4)",
        width: "fit-content",
      }}
    >
      <div className="wallpaper" aria-hidden="true" style={{ position: "absolute" }} />
      {children}
    </div>
  );
}

function Tile({ card, size }: { card: Card; size: WidgetSize }) {
  const [w, h] = spanOf(size);
  return (
    <div style={{ gridColumn: `span ${w}`, gridRow: `span ${h}`, minHeight: 0, display: "grid" }}>
      <div style={{ display: "grid", minHeight: 0 }}>
        <Widget
          title={card.title}
          hue={card.app.hue}
          appIcon={card.app.icon}
          size={size}
          shape={card.shape}
          state={card.state ?? "ready"}
          note={card.note}
        >
          {card.body()}
        </Widget>
      </div>
    </div>
  );
}

export const Escritorio: Story = {
  render: () => (
    <Grid columns={12}>
      {CARDS.map((card, index) => (
        <Tile key={index} card={card} size={card.sizes[0]!} />
      ))}
    </Grid>
  ),
};

export const Movil: Story = {
  render: () => (
    <Grid columns={4}>
      {CARDS.slice(0, 14).map((card, index) => (
        <Tile key={index} card={card} size={card.sizes[0]!} />
      ))}
    </Grid>
  ),
};

export const TodosLosTamanos: Story = {
  render: () => (
    <Grid columns={12}>
      {CARDS.flatMap((card, index) =>
        card.sizes.map((size) => <Tile key={`${index}-${size}`} card={card} size={size} />),
      )}
    </Grid>
  ),
};

export { APPS };
