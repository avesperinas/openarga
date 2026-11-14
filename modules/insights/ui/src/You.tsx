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
import { currentLocale, t } from "./lang";

export function grouped(traits: Trait[]): { facet: Facet; traits: Trait[] }[] {
  return FACET_ORDER.map((facet) => ({
    facet,
    traits: traits.filter((one) => one.facet === facet && one.status === "confirmed"),
  })).filter((group) => group.traits.length > 0);
}

const MINUTES = ["5", "10", "15", "20", "30"].map((value) => ({ value, label: `${value} min` }));
const RHYTHMS: { value: Settings["questions"]; label: string }[] = [
  { value: "never", get label() { return t("rhythm.never"); } },
  { value: "sometimes", get label() { return t("rhythm.sometimes"); } },
  { value: "daily", get label() { return t("rhythm.daily"); } },
];
const LEVELS = ["A2", "B1", "B2", "C1"].map((value) => ({ value, label: value }));
const KINDS = [
  { value: "magazine", get label() { return t("source_kind.magazine"); } },
  { value: "blog", get label() { return t("source_kind.blog"); } },
  { value: "podcast", get label() { return t("source_kind.podcast"); } },
  { value: "video", get label() { return t("source_kind.video"); } },
  { value: "media", get label() { return t("source_kind.media"); } },
  { value: "reference", get label() { return t("source_kind.reference"); } },
  { value: "forum", get label() { return t("source_kind.forum"); } },
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
      .catch((error: unknown) => setProblem(error instanceof Error ? error.message : t("error.save")));

  const proposed = tastes?.traits.filter((one) => one.status === "proposed") ?? [];

  return (
    <Screen>
      <ScreenHeader eyebrow={t("you.eyebrow", { name: app.name })} title={t("nav.you")} />
      <OfflineNotice />
      {problem && <Notice tone="warning">{problem}</Notice>}
      {found.loading && !tastes && <Skeleton label={t("you.loading")} />}
      {!tastes && found.error && <ErrorState title={t("you.failed")} detail={found.error.message} onRetry={found.refresh} />}

      {tastes && (
        <>
          {!tastes.onboarding.done && (
            <Notice
              title={t("today.meet")}
              action={{ label: tastes.onboarding.answered ? t("you.continue") : t("today.start"), onClick: onStart }}
            >
              {tastes.onboarding.answered
                ? t("you.progress", { done: tastes.onboarding.answered, total: tastes.onboarding.total })
                : t("you.meet_detail")}
            </Notice>
          )}

          {proposed.length > 0 && (
            <Section title={t("you.is_it")} count={proposed.length}>
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
            <EmptyState icon="spark" hue={5} title={t("you.empty", { name: app.name })} action={{ label: t("you.tell_it"), icon: "plus", onClick: () => setAdding(true) }}>
              {t("you.empty_detail")}
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
            {t("you.tell_something")}
          </Button>

          <Section title={t("you.topics")} count={tastes.families.length}>
            <Card>
              {tastes.families.map((family) => (
                <div key={family.key}>
                  <TopicChip name={family.name} glyph={glyphOf(family)} hue={family.hue} size="small" />
                  <ChoiceChips
                    label={t("you.how_much", { name: family.name })}
                    options={WEIGHTS}
                    value={String(family.weight)}
                    onChange={(weight) => void after(changeFamily(family.key, { weight: Number(weight) }))}
                  />
                </div>
              ))}
            </Card>
          </Section>

          <PillSettings settings={tastes.settings} onChange={(change) => void after(saveSettings(change))} />

          <Section title={t("you.sources")}>
            {tastes.families.map((family) => {
              const mine = tastes.sources.filter((one) => one.family_key === family.key);
              return (
                <Collapsible key={family.key} title={family.name} subtitle={t("you.in_use", { count: mine.filter((one) => !one.hidden).length })}>
                  <ToggleList label={t("you.sources_of", { name: family.name })}>
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
                    {t("you.add_source")}
                  </Button>
                </Collapsible>
              );
            })}
          </Section>

          <Section title={t("you.told")} action={{ label: t("action.edit"), onClick: onSettings }}>
            <Card>
              {profile?.about.trim() ? (
                <Prose text={profile.about} />
              ) : (
                <Prose text={t("you.told_empty")} />
              )}
            </Card>
          </Section>
        </>
      )}

      {adding && <AddTrait onClose={() => setAdding(false)} onSave={(facet, label, stance) => after(addTrait(facet, label, stance))} />}
      {source && tastes && <AddSource family={source} tastes={tastes} onClose={() => setSource(null)} onSave={(body) => after(addSource(body))} />}
      {forgetting && (
        <ConfirmDelete
          title={t("you.forget_confirm")}
          subject={forgetting.label}
          consequence={t("you.forget_consequence", { name: app.name })}
          action={t("you.forget")}
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
    <Section title={t("today.title")}>
      <Card>
        <ToggleList>
          <ToggleRow
            name={t("you.daily_pill")}
            detail={t("you.daily_pill_detail")}
            checked={settings.pill_on}
            onChange={(on) => onChange({ pill_on: on })}
          />
        </ToggleList>
        <TextField
          label={t("you.what_time")}
          type="time"
          value={time}
          onChange={setTime}
          onBlur={() => time !== settings.pill_time && /^\d\d:\d\d$/.test(time) && onChange({ pill_time: time })}
        />
        <ChoiceChips
          label={t("you.how_long")}
          options={MINUTES}
          value={String(settings.pill_minutes)}
          onChange={(minutes) => onChange({ pill_minutes: Number(minutes) as Settings["pill_minutes"] })}
        />
        <SelectField
          label={t("you.weekly_language")}
          options={LANGUAGES}
          value={settings.pill_language ?? "none"}
          onChange={(language) => onChange({ pill_language: language })}
        />
        {settings.pill_language && (
          <ChoiceChips label={t("you.level")} options={LEVELS} value={settings.pill_level} onChange={(level) => onChange({ pill_level: level })} />
        )}
        <ChoiceChips
          label={t("you.questions")}
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
      title={t("you.tell_something")}
      onClose={onClose}
      action={{
        label: t("action.save"),
        disabled: !label.trim(),
        onClick: () => void onSave(facet, label.trim(), Number(stance)).then(onClose),
      }}
    >
      <SelectField
        label={t("you.what_kind")}
        options={FACET_ORDER.map((value) => ({ value, label: FACETS[value].label }))}
        value={facet}
        onChange={(value) => {
          setFacet(value);
          if (value === "avoid") setStance("-2");
        }}
      />
      <TextField label={t("you.what")} value={label} onChange={setLabel} placeholder={t("you.what_placeholder")} />
      <ChoiceChips label={t("you.how_much_short")} options={STANCES} value={stance} onChange={setStance} />
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
  const [language, setLanguage] = useState<string>(currentLocale());
  const valid = name.trim().length > 0 && /^https:\/\/\S{3,}$/.test(url.trim());
  const familyName = tastes.families.find((one) => one.key === family)?.name ?? family;
  return (
    <Sheet
      title={t("you.source_for", { name: familyName })}
      onClose={onClose}
      action={{
        label: t("action.add"),
        disabled: !valid,
        onClick: () => void onSave({ family_key: family, name: name.trim(), kind, language, url: url.trim() }).then(onClose),
      }}
    >
      <TextField label={t("you.source_name")} value={name} onChange={setName} />
      <TextField label={t("you.source_url")} value={url} onChange={setUrl} />
      <SelectField label={t("you.what_kind")} options={KINDS} value={kind} onChange={setKind} />
      <ChoiceChips
        label={t("you.language")}
        options={["es", "en", "de", "fr"].map((value) => ({ value, label: t(`taste_language.${value}`) }))}
        value={language}
        onChange={setLanguage}
      />
    </Sheet>
  );
}
