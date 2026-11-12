import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { Sankey } from "../src/index";

const meta: Meta<typeof Sankey> = { title: "Gráficas/Diagrama de flujo", component: Sankey };
export default meta;

const euros = (value: number) => `${value.toLocaleString("es-ES")} €`;

export const TuYLoComun: StoryObj = {
  render: () => (
    <Sankey
      label="Tú y lo común"
      format={euros}
      nodes={[
        { id: "salary", name: "Salario", column: 0, kind: "income" },
        { id: "bonus", name: "Extra", column: 0, kind: "income" },
        { id: "me", name: "Tú", column: 1, kind: "you" },
        { id: "other", name: "Alguien", column: 1, kind: "member" },
        { id: "common", name: "Común", column: 2, kind: "common" },
        { id: "fun", name: "Ocio", column: 3, kind: "expense" },
        { id: "transport", name: "Transporte", column: 3, kind: "expense" },
        { id: "saved", name: "Ahorro", column: 3, kind: "saving" },
        { id: "rent", name: "Alquiler", column: 3, kind: "expense" },
        { id: "food", name: "Supermercado", column: 3, kind: "expense" },
      ]}
      links={[
        { source: "salary", target: "me", value: 2400 },
        { source: "bonus", target: "me", value: 300 },
        { source: "me", target: "common", value: 1100 },
        { source: "other", target: "common", value: 900 },
        { source: "me", target: "fun", value: 350 },
        { source: "me", target: "transport", value: 150 },
        { source: "me", target: "saved", value: 1100 },
        { source: "common", target: "rent", value: 1200 },
        { source: "common", target: "food", value: 800 },
      ]}
    />
  ),
};
