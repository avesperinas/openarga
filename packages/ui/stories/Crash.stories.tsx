import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../controls.css";
import { CrashBoundary } from "../src/index";

const meta = { title: "Estados/Una pantalla que falla", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Broken(): React.ReactNode {
  throw new TypeError("Cannot read properties of undefined (reading 'toFixed')");
}

export const Falla: Story = {
  render: () => (
    <CrashBoundary home="/training/">
      <Broken />
    </CrashBoundary>
  ),
};
