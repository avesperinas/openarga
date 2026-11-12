import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../controls.css";
import "../library.css";
import { ICON_STYLES, type IconStyle, PreviewChoices } from "../src/index";
import plannerInk from "../../../modules/planner/ui/public/icon-ink.svg?url";
import plannerPaper from "../../../modules/planner/ui/public/icon-paper.svg?url";
import plannerSolid from "../../../modules/planner/ui/public/icon-solid.svg?url";
import trainingInk from "../../../modules/training/ui/public/icon-ink.svg?url";
import trainingPaper from "../../../modules/training/ui/public/icon-paper.svg?url";
import trainingSolid from "../../../modules/training/ui/public/icon-solid.svg?url";

const meta = { title: "Elegir viendo cómo queda", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const ICONS: Record<IconStyle, string[]> = {
  solid: [plannerSolid, trainingSolid],
  ink: [plannerInk, trainingInk],
  paper: [plannerPaper, trainingPaper],
};

export const AcabadoDeLosIconos: Story = {
  render: function Render() {
    const [value, setValue] = React.useState<IconStyle>("solid");
    return (
      <div style={{ maxWidth: 480 }}>
        <PreviewChoices
          label="Iconos"
          value={value}
          onChange={setValue}
          options={ICON_STYLES.map((style) => ({
            ...style,
            preview: ICONS[style.value].map((src) => <img key={src} src={src} alt="" />),
          }))}
        />
      </div>
    );
  },
};
