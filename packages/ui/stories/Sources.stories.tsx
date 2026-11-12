import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { InletSettings, type InletValues, type SourceAnswers, type SourceAsk, SourceQuestions } from "../src/index";

const meta: Meta = { title: "Controles/Enchufar una fuente" };
export default meta;

const base = {
  source: null,
  depends_on: null,
  optional: false,
  none_label: null,
  default: null,
  choices: [],
  defaults: [],
  carries: [] as [string, string][],
  placeholder: "",
  help: "",
};

const asks: SourceAsk[] = [
  { ...base, key: "team", kind: "lookup", label: "Equipo", placeholder: "Escribe un nombre…" },
  {
    ...base,
    key: "sessions",
    kind: "checks",
    label: "Sesiones",
    choices: [
      { value: "race", label: "Carrera" },
      { value: "practice", label: "Libres" },
    ],
    defaults: ["race"],
  },
  { ...base, key: "url", kind: "url", label: "Dirección", placeholder: "https://… o webcal://…" },
];

const search = async (_ask: string, query?: string) => ({
  results: query ? [{ code: "1", name: `Equipo ${query}`, detail: "Liga de prueba" }] : [],
  failed: null,
});

function Form() {
  const [answers, setAnswers] = React.useState<SourceAnswers>({});
  const [values, setValues] = React.useState<InletValues>({ name: "Equipo de prueba", tone: 2 });
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", maxWidth: "26rem" }}>
      <SourceQuestions asks={asks} answers={answers} onChange={setAnswers} search={search} onError={() => undefined} />
      <InletSettings
        title="En Planner"
        settings={[
          { key: "name", kind: "text", label: "Nombre de la capa" },
          { key: "tone", kind: "tone", label: "Color" },
        ]}
        values={values}
        onChange={setValues}
      />
    </div>
  );
}

export const Preguntas: StoryObj = { render: () => <Form /> };
