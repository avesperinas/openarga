import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../stories/**/*.stories.tsx"],
  framework: { name: "@storybook/react-vite", options: {} },
  addons: [],
  core: { disableTelemetry: true },
  staticDirs: [
    { from: "../geo", to: "/geo" },
    { from: "../../../shell/public/wallpapers", to: "/wallpapers" },
  ],
};

export default config;
