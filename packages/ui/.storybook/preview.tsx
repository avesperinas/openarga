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
      description: "Explicit theme, the one data-theme sets",
      defaultValue: "light",
      toolbar: {
        title: "Theme",
        items: [
          { value: "light", title: "Light" },
          { value: "dark", title: "Dark" },
        ],
      },
    },
    glassOpacity: {
      description: "The Transparency setting. At 1.00 it is the legibility floor.",
      defaultValue: "0.55",
      toolbar: {
        title: "Transparency",
        items: ["0.35", "0.55", "0.75", "1"],
      },
    },
  },
  parameters: { layout: "fullscreen", controls: { disable: true } },
};

export default preview;
