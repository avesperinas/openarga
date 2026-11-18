import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { FilePreview, configureRegional } from "../src/index";

const meta = { title: "Piezas/FilePreview", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="glass" style={{ display: "grid", gap: "var(--space-4)", width: "min(32rem, 100%)", boxSizing: "border-box", padding: "var(--space-6)" }}>
      {children}
    </div>
  );
}

const ROWS = [
  ["2030-01-03", "Groceries", "-42.10"],
  ["2030-01-04", "Salary", "1800.00"],
  ["2030-01-05", "Rent", "-650.00"],
];

function sample(total: number | undefined, rows = ROWS) {
  return (
    <Panel>
      <FilePreview name="statement.csv" size={2048} columns={["Date", "Description", "Amount"]} rows={rows} total={total} onRemove={() => undefined} />
    </Panel>
  );
}

export const English: Story = {
  beforeEach: () => {
    configureRegional({ locale: "en-US" });
    return () => configureRegional({ locale: "es-ES" });
  },
  render: () => sample(42),
};

export const Spanish: Story = {
  beforeEach: () => {
    configureRegional({ locale: "es-ES" });
  },
  render: () => sample(42),
};

export const Empty: Story = {
  beforeEach: () => {
    configureRegional({ locale: "en-US" });
    return () => configureRegional({ locale: "es-ES" });
  },
  render: () => sample(undefined, []),
};
