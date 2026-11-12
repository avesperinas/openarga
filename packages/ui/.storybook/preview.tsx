import type { Decorator, Preview } from "@storybook/react";
import * as React from "react";

import "../tokens.css";
import "../widget.css";
import "../controls.css";
import "../calendar.css";

const onTheWash: Decorator = (Story, context) => {
  const { theme, glassOpacity } = context.globals;
  document.documentElement.dataset.theme = theme;
  return (
    <div
      data-theme={theme}
      style={{
        background: "var(--bg-wash)",
        minHeight: "100vh",
        padding: "var(--space-8)",
        ["--glass-opacity" as string]: glassOpacity,
      }}
    >
      <Story />
    </div>
  );
};

const preview: Preview = {
  decorators: [onTheWash],
  globalTypes: {
    theme: {
      description: "Tema explícito, el que pone data-theme",
      defaultValue: "light",
      toolbar: {
        title: "Tema",
        items: [
          { value: "light", title: "Claro" },
          { value: "dark", title: "Oscuro" },
        ],
      },
    },
    glassOpacity: {
      description: "El ajuste de Transparencia. En 1,00 es el suelo de legibilidad.",
      defaultValue: "0.55",
      toolbar: {
        title: "Transparencia",
        items: ["0.35", "0.55", "0.75", "1"],
      },
    },
  },
  parameters: { layout: "fullscreen", controls: { disable: true } },
};

export default preview;
