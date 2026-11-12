import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { Icon, IconBadge, type IconName } from "../src/index";
import "../library.css";

const meta = {
  title: "Iconos",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const NAMES: IconName[] = [
  "atom",
  "chip",
  "spark",
  "compass",
  "film",
  "headphones",
  "lightbulb",
  "food",
  "music",
  "landmark",
  "party",
  "mountain",
  "bookmark",
  "cup",
  "umbrella",
  "castle",
  "parking",
  "bed",
  "bag",
  "binoculars",
  "push",
  "pull",
  "leg",
  "kettlebell",
  "dumbbell",
  "today",
  "modules",
  "settings",
  "edit",
  "done",
  "plus",
  "minus",
  "close",
  "chevron-left",
  "chevron-right",
  "chevron-up",
  "chevron-down",
  "target",
  "bolt",
  "calendar",
  "chart",
  "flame",
  "heart",
  "image",
  "sun",
  "moon",
  "system",
  "trash",
  "book",
  "basket",
  "timer",
  "undo",
  "expand",
  "arrow-right",
  "globe",
  "map",
  "pin",
  "plane",
  "train",
  "car",
  "bus",
  "boat",
  "play",
  "pause",
  "filter",
  "paw",
  "shield",
  "home",
  "id-card",
  "contract",
  "appliance",
  "ticket",
  "alert",
  "repeat",
  "box",
  "search",
  "phone",
  "mail",
  "copy",
  "clip",
  "link",
  "camera",
  "file",
  "external",
  "clock",
  "skip",
];

const SIZES = ["--icon-s", "--icon-m", "--icon-l", "--icon-xl"] as const;

export const Todos: Story = {
  render: () => (
    <table style={{ borderSpacing: "var(--space-4)", color: "var(--fg)" }}>
      <tbody>
        {NAMES.map((name) => (
          <tr key={name}>
            {SIZES.map((size) => (
              <td key={size} style={{ ["--size" as string]: `var(${size})` }}>
                <span style={{ display: "inline-flex", width: "var(--size)", height: "var(--size)" }}>
                  <Icon name={name} />
                </span>
              </td>
            ))}
            <td style={{ font: "var(--text-footnote) var(--font-sans)", color: "var(--fg-muted)" }}>
              {name}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  ),
};

export const Placas: Story = {
  render: () => (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-4)" }}>
      {(
        [
          ["push", 4],
          ["pull", 2],
          ["leg", 1],
          ["kettlebell", 5],
          ["dumbbell", 8],
          ["flame", 3],
          ["book", 7],
          ["bolt", 6],
        ] as const
      ).map(([name, hue]) => (
        <IconBadge key={name} name={name} hue={hue} />
      ))}
    </div>
  ),
};
