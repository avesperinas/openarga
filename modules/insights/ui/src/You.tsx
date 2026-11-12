import { invalidate, useResource } from "@openarga/app";
import {
  Button,
  Card,
  ChoiceChips,
  Collapsible,
  ConfirmDelete,
  EmptyState,
  ErrorState,
  Notice,
  OfflineNotice,
  Prose,
  Screen,
  Section,
  SelectField,
  Sheet,
  Skeleton,
  TextField,
  ToggleList,
  ToggleRow,
  TopicChip,
  TraitRow,
} from "@openarga/ui";
import { useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Facet,
  PROFILE,
  type Settings,
  TASTES,
  TODAY,
  type Tastes,
  type Trait,
  addSource,
  addTrait,
  changeFamily,
  changeSource,
  changeTrait,
  forgetTrait,
  readProfile,
  readTastes,
  saveSettings,
} from "./api";
import { ScreenHeader, useApp } from "./Header";
import { FACETS, FACET_ORDER, LANGUAGES, SOURCES, STANCES, WEIGHTS, glyphOf } from "./taste-words";

export function grouped(traits: Trait[]): { facet: Facet; traits: Trait[] }[] {
  return FACET_ORDER.map((facet) => ({
    facet,
    traits: traits.filter((one) => one.facet === facet && one.status === "confirmed"),
  })).filter((group) => group.traits.length > 0);
}

const MINUTES = ["5", "10", "15", "20", "30"].map((value) => ({ value, label: `${value} min` }));
const RHYTHMS: { value: Settings["questions"]; label: string }[] = [
  { value: "never", label: "Nunca" },
  { value: "sometimes", label: "De vez en cuando" },
  { value: "daily", label: "Cada día" },
];
const LEVELS = ["A2", "B1", "B2", "C1"].map((value) => ({ value, label: value }));
const KINDS = [
  { value: "magazine", label: "Revista" },
  { value: "blog", label: "Blog" },
  { value: "podcast", label: "Podcast" },
  { value: "video", label: "Vídeo" },
  { value: "media", label: "Medio" },
  { value: "reference", label: "Referencia" },
  { value: "forum", label: "Foro" },
];

export function YouScreen({ onStart, onSettings }: { onStart: () => void; onSettings: () => void }) {
  const app = useApp();
  const found = useResource(TASTES, readTastes, { persist: true });
  const profile = useResource(PROFILE, readProfile, { persist: true }).data;
  const tastes = found.data ?? null;
  const [problem, setProblem] = useState("");
  const [forgetting, setForgetting] = useState<Trait | null>(null);
  const [adding, setAdding] = useState(false);
  const [source, setSource] = useState<string | null>(null);

  const after = (promise: Promise<unknown>) =>
    promise
      .then(() => {
        invalidate(TASTES);
        invalidate(TODAY);
      })
      .catch((error: unknown) => setProblem(error instanceof Error ? error.message : "No se pudo guardar."));

  const proposed = tastes?.traits.filter((one) => one.status === "proposed") ?? [];

  return (
    <Screen>
      <ScreenHeader eyebrow={`Lo que ${app.name} sabe de ti`} title="Tú" />
      <OfflineNotice />
      {problem && <Notice tone="warning">{problem}</Notice>}
      {found.loading && !tastes && <Skeleton label="Abriendo lo que sabe de ti" />}
      {!tastes && found.error && <ErrorState title="No se pudo abrir" detail={found.error.message} onRetry={found.refresh} />}

      {tastes && (
        <>
          {!tastes.onboarding.done && (
            <Notice
              title="Que te conozca"
              action={{ label: tastes.onboarding.answered ? "Seguir" : "Empezar", onClick: onStart }}
            >
              {tastes.onboarding.answered
                ? `Llevas ${tastes.onboarding.answered} de ${tastes.onboarding.total}. Quedan unas pocas de un toque.`
                : "Doce preguntas de un toque, tres minutos. Es lo que más rápido le enseña qué te gusta."}
            </Notice>
          )}

          {proposed.length > 0 && (
            <Section title="¿Es así?" count={proposed.length}>
              <Card>
                {proposed.map((trait) => (
                  <TraitRow
                    key={trait.id}
                    icon={FACETS[trait.facet].icon}
                    label={trait.label}
                    stance={trait.stance}
                    source={`${FACETS[trait.facet].label} · ${SOURCES[trait.source]}`}
                    evidence={trait.evidence}
                    proposed
                    onConfirm={() => void after(changeTrait(trait.id, { status: "confirmed" }))}
                    onReject={() => void after(changeTrait(trait.id, { status: "rejected" }))}
                  />
                ))}
              </Card>
            </Section>
          )}

          {grouped(tastes.traits).length === 0 && proposed.length === 0 ? (
            <EmptyState icon="spark" hue={5} title={`${app.name} todavía no sabe nada de tus gustos`} action={{ label: "Contárselo", icon: "plus", onClick: () => setAdding(true) }}>
              Contesta «Que te conozca» o cuéntale algo: un tema, un autor, algo de lo que no quieres que te hable. Y en unos días
              te propondrá lo que vea en tus lecturas, tus estudios y tus viajes.
            </EmptyState>
          ) : (
            grouped(tastes.traits).map((group) => (
              <Section
                key={group.facet}
                title={FACETS[group.facet].label}
                count={group.traits.length}
              >
                <Card>
                  {group.traits.map((trait) => (
                    <TraitRow
                      key={trait.id}
                      icon={FACETS[trait.facet].icon}
                      label={trait.label}
                      stance={trait.stance}
                      source={SOURCES[trait.source]}
                      evidence={trait.evidence}
                      proposed={false}
                      onForget={() => setForgetting(trait)}
                    />
                  ))}
                </Card>
              </Section>
            ))
          )}
          <Button variant="secondary" icon="plus" onClick={() => setAdding(true)}>
            Contarle algo de ti
          </Button>

          <Section title="Tus temas" count={tastes.families.length}>
            <Card>
              {tastes.families.map((family) => (
                <div key={family.key}>
                  <TopicChip name={family.name} glyph={glyphOf(family)} hue={family.hue} size="small" />
                  <ChoiceChips
                    label={`Cuánto te interesa ${family.name}`}
                    options={WEIGHTS}
                    value={String(family.weight)}
                    onChange={(weight) => void after(changeFamily(family.key, { weight: Number(weight) }))}
                  />
                </div>
              ))}
            </Card>
          </Section>

          <PillSettings settings={tastes.settings} onChange={(change) => void after(saveSettings(change))} />

          <Section title="Tus fuentes">
            {tastes.families.map((family) => {
              const mine = tastes.sources.filter((one) => one.family_key === family.key);
              return (
                <Collapsible key={family.key} title={family.name} subtitle={`${mine.filter((one) => !one.hidden).length} en uso`}>
                  <ToggleList label={`Fuentes de ${family.name}`}>
                    {mine.map((one) => (
                      <ToggleRow
                        key={one.id}
                        name={one.name}
                        detail={`${KINDS.find((kind) => kind.value === one.kind)?.label ?? one.kind} · ${one.language}`}
                        checked={!one.hidden}
                        onChange={(on) => void after(changeSource(one.id, !on))}
                      />
                    ))}
                  </ToggleList>
                  <Button variant="plain" icon="plus" onClick={() => setSource(family.key)}>
                    Añadir una tuya
                  </Button>
                </Collapsible>
              );
            })}
          </Section>

          <Section title="Lo que le has contado" action={{ label: "Editar", onClick: onSettings }}>
            <Card>
              {profile?.about.trim() ? (
                <Prose text={profile.about} />
              ) : (
                <Prose text="Todavía nada. En Ajustes puedes contarle qué te importa, tu contexto y de qué no quieres que te hable." />
              )}
            </Card>
          </Section>
        </>
      )}

      {adding && <AddTrait onClose={() => setAdding(false)} onSave={(facet, label, stance) => after(addTrait(facet, label, stance))} />}
      {source && tastes && <AddSource family={source} tastes={tastes} onClose={() => setSource(null)} onSave={(body) => after(addSource(body))} />}
      {forgetting && (
        <ConfirmDelete
          title="¿Olvidar esto?"
          subject={forgetting.label}
          consequence={`${app.name} deja de tenerlo en cuenta. Si te lo vuelve a proponer, lo verás aquí.`}
          action="Olvidar"
          onCancel={() => setForgetting(null)}
          onConfirm={() => {
            const trait = forgetting;
            setForgetting(null);
            void after(forgetTrait(trait.id));
          }}
        />
      )}
      <AppVersion />
    </Screen>
  );
}

function PillSettings({ settings, onChange }: { settings: Settings; onChange: (change: Partial<Settings>) => void }) {
  const [time, setTime] = useState(settings.pill_time);
  return (
    <Section title="Tu píldora">
      <Card>
        <ToggleList>
          <ToggleRow
            name="La píldora de cada día"
            detail="Con los datos del día y lo recomendado"
            checked={settings.pill_on}
            onChange={(on) => onChange({ pill_on: on })}
          />
        </ToggleList>
        <TextField
          label="A qué hora"
          type="time"
          value={time}
          onChange={setTime}
          onBlur={() => time !== settings.pill_time && /^\d\d:\d\d$/.test(time) && onChange({ pill_time: time })}
        />
        <ChoiceChips
          label="Cuánto tiempo"
          options={MINUTES}
          value={String(settings.pill_minutes)}
          onChange={(minutes) => onChange({ pill_minutes: Number(minutes) as Settings["pill_minutes"] })}
        />
        <SelectField
          label="Una a la semana en el idioma que aprendes"
          options={LANGUAGES}
          value={settings.pill_language ?? "none"}
          onChange={(language) => onChange({ pill_language: language })}
        />
        {settings.pill_language && (
          <ChoiceChips label="Tu nivel" options={LEVELS} value={settings.pill_level} onChange={(level) => onChange({ pill_level: level })} />
        )}
        <ChoiceChips
          label="Cuánto te pregunta"
          options={RHYTHMS}
          value={settings.questions}
          onChange={(questions) => onChange({ questions })}
        />
      </Card>
    </Section>
  );
}

function AddTrait({ onClose, onSave }: { onClose: () => void; onSave: (facet: Facet, label: string, stance: number) => Promise<unknown> }) {
  const [facet, setFacet] = useState<Facet>("topic");
  const [label, setLabel] = useState("");
  const [stance, setStance] = useState("1");
  return (
    <Sheet
      title="Contarle algo de ti"
      onClose={onClose}
      action={{
        label: "Guardar",
        disabled: !label.trim(),
        onClick: () => void onSave(facet, label.trim(), Number(stance)).then(onClose),
      }}
    >
      <SelectField
        label="Qué es"
        options={FACET_ORDER.map((value) => ({ value, label: FACETS[value].label }))}
        value={facet}
        onChange={(value) => {
          setFacet(value);
          if (value === "avoid") setStance("-2");
        }}
      />
      <TextField label="Qué" value={label} onChange={setLabel} placeholder="Ciencia ficción, Ursula K. Le Guin, fútbol…" />
      <ChoiceChips label="Cuánto" options={STANCES} value={stance} onChange={setStance} />
    </Sheet>
  );
}

function AddSource({
  family,
  tastes,
  onClose,
  onSave,
}: {
  family: string;
  tastes: Tastes;
  onClose: () => void;
  onSave: (body: { family_key: string; name: string; kind: string; language: string; url: string }) => Promise<unknown>;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("https://");
  const [kind, setKind] = useState("magazine");
  const [language, setLanguage] = useState("es");
  const valid = name.trim().length > 0 && /^https:\/\/\S{3,}$/.test(url.trim());
  const familyName = tastes.families.find((one) => one.key === family)?.name ?? family;
  return (
    <Sheet
      title={`Una fuente tuya para ${familyName}`}
      onClose={onClose}
      action={{
        label: "Añadir",
        disabled: !valid,
        onClick: () => void onSave({ family_key: family, name: name.trim(), kind, language, url: url.trim() }).then(onClose),
      }}
    >
      <TextField label="Nombre" value={name} onChange={setName} />
      <TextField label="Dirección" value={url} onChange={setUrl} />
      <SelectField label="Qué es" options={KINDS} value={kind} onChange={setKind} />
      <ChoiceChips
        label="Idioma"
        options={[
          { value: "es", label: "Español" },
          { value: "en", label: "Inglés" },
          { value: "de", label: "Alemán" },
          { value: "fr", label: "Francés" },
        ]}
        value={language}
        onChange={setLanguage}
      />
    </Sheet>
  );
}
