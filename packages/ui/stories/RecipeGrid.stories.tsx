import type { Meta, StoryObj } from "@storybook/react";

import { RecipeGrid } from "../src/index";
import "../library.css";

const meta = {
  title: "Biblioteca/RecipeGrid",
  component: RecipeGrid,
  parameters: { layout: "padded" },
} satisfies Meta<typeof RecipeGrid>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Bizcocho: Story = {
  args: {
    label: "Cómo se monta el bizcocho",
    columns: 5,
    bands: [
      { id: "molde", label: "Untar y enharinar el molde" },
      { id: "horno", label: "Precalentar el horno a 170°", note: "10 min" },
    ],
    rows: [
      { id: 1, amount: "115 g", label: "Mantequilla" },
      { id: 2, amount: "200 g", label: "Azúcar" },
      { id: 3, amount: "1 cdta", label: "Vainilla" },
      { id: 4, amount: "60 ml", label: "Café" },
      { id: 5, amount: "2", label: "Huevos" },
      { id: 6, amount: "80 g", label: "Harina" },
      { id: 7, amount: "80 g", label: "Cacao" },
      { id: 8, amount: "1/4 cdta", label: "Bicarbonato" },
      { id: 9, amount: "1/4 cdta", label: "Sal" },
    ],
    cells: [
      { id: 3, label: "Derretir", note: "3 min", column: 1, row: 1, span: 1 },
      { id: 4, label: "Mezclar", note: "3 min", column: 2, row: 1, span: 4 },
      { id: 5, label: "Batir", note: "2 min", column: 3, row: 1, span: 5 },
      { id: 6, label: "Incorporar", note: "4 min", column: 4, row: 1, span: 9 },
      {
        id: 7,
        label: "Hornear",
        detail: "170°, hasta que el palillo salga limpio",
        note: "35 min · corre solo",
        column: 5,
        row: 1,
        span: 9,
        attended: false,
      },
    ],
  },
};

export const DosCadenas: Story = {
  args: {
    label: "Cómo se monta la porrusalda",
    columns: 3,
    rows: [
      { id: 1, amount: "400 g", label: "Puerro" },
      { id: 2, amount: "30 ml", label: "Aceite de oliva" },
      { id: 3, amount: "600 g", label: "Patata" },
      { id: 4, amount: "200 g", label: "Bacalao", unused: true },
    ],
    cells: [
      { id: 1, label: "Picar", detail: "El puerro en rodajas", column: 1, row: 1, span: 1 },
      { id: 2, label: "Pelar", detail: "Cascar las patatas", column: 1, row: 3, span: 1 },
      { id: 3, label: "Pochar", note: "10 min", column: 2, row: 1, span: 2 },
      {
        id: 4,
        label: "Cocer",
        detail: "A fuego lento",
        note: "30 min · corre solo",
        column: 3,
        row: 1,
        span: 3,
        attended: false,
      },
    ],
  },
};
