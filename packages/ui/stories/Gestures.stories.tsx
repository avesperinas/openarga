import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { List, PullToRefresh, SwipeRow, ListRow } from "../src/index";

const meta = { title: "Gestos", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const DeslizarYRefrescar: Story = {
  render: function Render() {
    const [items, setItems] = React.useState(["Leche", "Pan", "Detergente"]);
    return (
      <div style={{ width: "min(24rem, 100%)" }}>
        <PullToRefresh onRefresh={() => new Promise((resolve) => setTimeout(resolve, 800))}>
          <List>
            {items.map((item) => (
              <SwipeRow
                key={item}
                label={item}
                actions={[{ label: "Quitar", icon: "trash", tone: "danger", onAction: () => setItems((all) => all.filter((one) => one !== item)) }]}
              >
                <ListRow title={item} />
              </SwipeRow>
            ))}
          </List>
        </PullToRefresh>
      </div>
    );
  },
};
