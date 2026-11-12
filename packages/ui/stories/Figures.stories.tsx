import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../controls.css";
import "../library.css";
import {
  Badge,
  Card,
  ConfirmButton,
  Delta,
  DisclosureList,
  DisclosureRow,
  Figures,
  HeadlineFigure,
  Hint,
  ProgressRing,
  Sequence,
  SequenceHint,
  SequenceRow,
  SequenceSeparator,
  Stepper,
  WeekDots,
} from "../src/index";

const meta = { title: "Cifras y filas", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const AlTerminar: Story = {
  render: () => (
    <div data-kind="pull" style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <Card>
        <Figures
          items={[
            { label: "minutos", value: 75 },
            { label: "series", value: 28 },
            { label: "récords", value: 2, lit: true },
          ]}
        />
      </Card>
      <Card>
        <HeadlineFigure label="Máximo estimado" value={119} unit="kg" change={{ text: "+6 kg en 3 meses", direction: "up" }} />
      </Card>
    </div>
  ),
};

function Session() {
  const [open, setOpen] = React.useState<string | null>("a");
  const [load, setLoad] = React.useState<number | null>(40);
  const [reps, setReps] = React.useState<number | null>(3);
  return (
    <div data-kind="pull" style={{ maxWidth: 390 }}>
      <DisclosureList label="Ejercicios">
        <DisclosureRow
          title="Dominadas"
          subtitle="3, 3 + 40 kg"
          tag="superserie"
          leading={<ProgressRing done={2} target={4} />}
          open={open === "a"}
          onToggle={() => setOpen(open === "a" ? null : "a")}
        >
          <Hint>La última vez, lun 7 sept: 3, 3, 2 + 40 kg</Hint>
          <Sequence>
            <li>
              <SequenceRow number={1} state="done" value="3 + 40 kg" onClick={() => undefined} label="Serie 1" />
            </li>
            <li>
              <SequenceRow number={2} state="done" value="3 + 40 kg" onClick={() => undefined} label="Serie 2" />
            </li>
            <li>
              <SequenceRow number={3} state="now" trailing={<ConfirmButton label="Confirmar serie 3" />}>
                <Stepper size="small" label="Lastre" value={load} step={2.5} unit="kg" onChange={setLoad} />
                <SequenceSeparator />
                <Stepper size="small" label="Reps" value={reps} step={1} onChange={setReps} />
              </SequenceRow>
              <SequenceHint>Corrigiendo la serie 3</SequenceHint>
            </li>
            <li>
              <SequenceRow number={4} state="todo" value="3 + 40 kg" />
            </li>
          </Sequence>
        </DisclosureRow>
        <DisclosureRow
          title="Remo en polea"
          subtitle="8, 8, 8, 7 × 65 kg"
          leading={<ProgressRing done={4} target={4} />}
          trailing={
            <>
              <Badge tone="positive">Récord</Badge>
              <Delta text="+1 rep" direction="up" />
            </>
          }
          open={open === "b"}
          onToggle={() => setOpen(open === "b" ? null : "b")}
        />
        <DisclosureRow
          title="Curl en polea"
          subtitle="4 × 10–12 · primera vez"
          leading={<ProgressRing done={0} target={4} />}
          open={open === "c"}
          onToggle={() => setOpen(open === "c" ? null : "c")}
        />
      </DisclosureList>
    </div>
  );
}

export const UnaSesion: Story = { render: () => <Session /> };

export const LaSemana: Story = {
  render: () => (
    <Card>
      <WeekDots
        size="large"
        label="3 de 5 esta semana"
        days={[
          { day: "2026-09-14", state: "met", kind: "push" },
          { day: "2026-09-15", state: "missed" },
          { day: "2026-09-16", state: "met", kind: "pull" },
          { day: "2026-09-17", state: "met", kind: "leg", today: true },
          { day: "2026-09-18", state: "future" },
          { day: "2026-09-19", state: "future" },
          { day: "2026-09-20", state: "future" },
        ]}
      />
    </Card>
  ),
};
