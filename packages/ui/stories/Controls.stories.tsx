import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import {
  AppBar,
  Button,
  CheckRow,
  ChoiceChips,
  ConfirmButton,
  ConfirmDelete,
  CopyField,
  CredentialField,
  DateField,
  Elapsed,
  IconButton,
  List,
  ListRow,
  MonthCalendar,
  SegmentedControl,
  Sheet,
  Slider,
  Stepper,
  Switch,
  SyncMark,
  TabBar,
  TextField,
} from "../src/index";

const meta = {
  title: "Controles",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="glass"
      style={{
        display: "grid",
        gap: "var(--space-4)",
        width: "min(24rem, 100%)",
        padding: "var(--space-6)",
      }}
    >
      {children}
    </div>
  );
}

export const Botones: Story = {
  render: () => (
    <Panel>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        <Button variant="primary" icon="done">
          Hecho
        </Button>
        <Button>Cancelar</Button>
        <Button variant="tinted" icon="plus">
          Añadir
        </Button>
        <Button variant="plain" size="small" icon="undo">
          Deshacer
        </Button>
      </div>
      <Button variant="destructive" icon="trash" block>
        Borrarlos con la pantalla
      </Button>
      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <IconButton icon="close" label="Cerrar" />
        <IconButton icon="chevron-left" label="Anterior" size="small" />
        <IconButton icon="trash" label="Borrar" size="small" variant="destructive" />
        <IconButton icon="chevron-right" label="Siguiente" size="small" disabled />
      </div>
    </Panel>
  ),
};

export const Segmentado: Story = {
  render: function Render() {
    const [theme, setTheme] = React.useState<"system" | "light" | "dark">("system");
    const [opacity, setOpacity] = React.useState(0.55);
    return (
      <Panel>
        <SegmentedControl
          label="Tema"
          value={theme}
          onChange={setTheme}
          options={[
            { value: "system", label: "Sistema", icon: "system" },
            { value: "light", label: "Claro", icon: "sun" },
            { value: "dark", label: "Oscuro", icon: "moon" },
          ]}
        />
        <Slider
          label="Transparencia"
          min={0.2}
          max={1}
          step={0.05}
          value={opacity}
          valueText={`${Math.round(opacity * 100)} por ciento`}
          onChange={setOpacity}
        />
      </Panel>
    );
  },
};

export const Interruptor: Story = {
  render: function Render() {
    const [on, setOn] = React.useState(true);
    return (
      <Panel>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span>Programación activa</span>
          <Switch label="Programación activa" checked={on} onChange={setOn} />
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span>Sin permiso</span>
          <Switch label="Sin permiso" checked={false} onChange={() => {}} disabled />
        </div>
      </Panel>
    );
  },
};

export const Lista: Story = {
  render: () => (
    <Panel>
      <List>
        <ListRow title="Eventos" detail="Ya colocado" hue={1} accessory="done" disabled />
        <ListRow title="Constancia" detail="2x2 · 2x4" hue={2} accessory="plus" />
        <ListRow title="Demo" detail="2x2 · 4x2" hue={5} accessory="plus" />
      </List>
    </Panel>
  ),
};

export const ParaMarcar: Story = {
  render: () => {
    const [cart, setCart] = React.useState<string[]>(["Pan"]);
    const toggle = (name: string) =>
      setCart((now) => (now.includes(name) ? now.filter((one) => one !== name) : [...now, name]));
    return (
      <Panel>
        <List>
          {[
            { name: "Leche", detail: "2" },
            { name: "Pan", detail: "" },
            { name: "Tomates", detail: "1 kg" },
          ].map((one) => (
            <CheckRow
              key={one.name}
              title={one.name}
              detail={one.detail || undefined}
              checked={cart.includes(one.name)}
              onToggle={() => toggle(one.name)}
              more={{ label: `Cambiar ${one.name}`, onClick: () => {} }}
            />
          ))}
        </List>
      </Panel>
    );
  },
};

export const Registrar: Story = {
  render: function Render() {
    const [variant, setVariant] = React.useState("smith");
    const [weight, setWeight] = React.useState<number | null>(62.5);
    const [reps, setReps] = React.useState<number | null>(8);
    const [confirmed, setConfirmed] = React.useState(false);
    const started = React.useMemo(() => new Date(Date.now() - 42 * 60_000).toISOString(), []);
    return (
      <div style={{ display: "grid", gap: "var(--space-4)", width: "min(24rem, 100%)" }}>
        <AppBar
          title="Leg"
          subtitle="Rotación 3 · día 3 de 3"
          back={{ icon: "chevron-left", label: "Hoy", onClick: () => undefined }}
          action={{ label: "Terminar", onClick: () => undefined }}
        />
        <Panel>
          <Elapsed since={started} label="Sesión" />
          <ChoiceChips
            label="Variante"
            value={variant}
            onChange={setVariant}
            options={[
              { value: "smith", label: "Sentadilla Smith" },
              { value: "barra", label: "Sentadilla barra" },
              { value: "prensa", label: "Prensa" },
            ]}
          />
          <div data-kind="leg" style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
            <span style={{ width: "var(--space-2)", height: "var(--space-2)", borderRadius: "50%", background: "var(--kind)" }} />
            <span>Tipo de sesión</span>
          </div>
          <Stepper label="Peso" value={weight} step={2.5} unit="kg" onChange={setWeight} />
          <Stepper label="Reps" value={reps} step={1} inputMode="numeric" onChange={setReps} />
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
            <Stepper size="small" label="Peso" value={weight} step={2.5} unit="kg" onChange={setWeight} />
            <span>×</span>
            <Stepper size="small" label="Reps" value={reps} step={1} inputMode="numeric" onChange={setReps} />
          </div>
          <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
            <ConfirmButton label="Confirmar serie 1" confirmed={confirmed} onClick={() => setConfirmed((c) => !c)} />
            <SyncMark state="saved" />
            <SyncMark state="sending" />
            <SyncMark state="pending" />
          </div>
          <Elapsed since={started} label="Descanso" size="large" />
        </Panel>
      </div>
    );
  },
};

export const App: Story = {
  render: function Render() {
    const [tab, setTab] = React.useState<"hoy" | "calendario" | "plan">("calendario");
    const [month, setMonth] = React.useState(8);
    const [name, setName] = React.useState("");
    const [open, setOpen] = React.useState(false);
    return (
      <div style={{ display: "grid", gap: "var(--space-4)", width: "min(24rem, 100%)" }}>
        <Panel>
          <MonthCalendar
            year={2026}
            month={month}
            today="2026-09-16"
            marks={{
              "2026-09-01": [{ kind: "push", label: "Push" }],
              "2026-09-02": [{ kind: "pull", label: "Pull" }],
              "2026-09-04": [{ kind: "leg", label: "Leg" }],
              "2026-09-14": [{ kind: "push", label: "Push" }, { kind: "other", label: "Core" }],
            }}
            weekBelow={(monday) => monday === "2026-09-07"}
            onPrevious={() => setMonth(month - 1)}
            onNext={() => setMonth(month + 1)}
          />
          <Button onClick={() => setOpen(true)}>Abrir hoja</Button>
        </Panel>
        {open && (
          <Sheet title="Nuevo ejercicio" onClose={() => setOpen(false)} action={{ label: "Crear", onClick: () => setOpen(false), disabled: !name }}>
            <TextField label="Nombre" value={name} onChange={setName} placeholder="Press banca" />
          </Sheet>
        )}
        <TabBar
          label="Secciones"
          active={tab}
          onSelect={setTab}
          items={[
            { id: "hoy", label: "Hoy", icon: "today" },
            { id: "calendario", label: "Calendario", icon: "calendar" },
            { id: "plan", label: "Plan", icon: "edit" },
          ]}
        />
      </div>
    );
  },
};

export const Copiar: Story = {
  render: () => (
    <Panel>
      <CopyField label="URL del servidor" value="https://arga.example/mcp" copy={async () => undefined} />
      <CopyField label="ID de cliente" value="claude" copy={async () => undefined} />
    </Panel>
  ),
};

export const Borrar: Story = {
  render: function Borrar() {
    const [open, setOpen] = React.useState(true);
    return (
      <Panel>
        <Button variant="plain" icon="trash" onClick={() => setOpen(true)}>
          Borrar receta
        </Button>
        {open && (
          <ConfirmDelete
            title="¿Borrar esta receta?"
            subject="Lentejas con verduras"
            consequence="Se pierden sus 9 ingredientes y 6 pasos. No se puede deshacer."
            action="Borrar receta"
            onCancel={() => setOpen(false)}
            onConfirm={() => setOpen(false)}
          />
        )}
      </Panel>
    );
  },
};

export const Credencial: Story = {
  render: function Credencial() {
    const [value, setValue] = React.useState("");
    return (
      <Panel>
        <CredentialField
          label="Token de Claude Code"
          help="Lo generas con `claude setup-token` en tu ordenador."
          configured
          hint="…a3f9"
          value={value}
          onChange={setValue}
          onSave={() => setValue("")}
          onRemove={() => undefined}
        />
      </Panel>
    );
  },
};

export const Fecha: Story = {
  render: function Fecha() {
    const [day, setDay] = React.useState("2026-10-02");
    return (
      <Panel>
        <DateField label="Desde" value={day} onChange={setDay} />
      </Panel>
    );
  },
};
