import {
  AppSettings,
  type BodyWeightHistory,
  BodyWeightCard,
  Button,
  Card,
  CheckChips,
  Hint,
  Section,
  Skeleton,
  Stepper,
  TextField,
  useT,
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { bandKinds } from "./Activities";
import {
  type ActivityType,
  type Gym,
  type Settings,
  createGym,
  listActivityTypes,
  readCatalogue,
  readToday,
  logWeight,
  readWeight,
  updateActivityType,
  updateGym,
  updateSettings,
} from "./api";
import { APP } from "./Header";

type Loaded = { settings: Settings; gyms: Gym[] };

export function SettingsScreen({ initial }: { initial?: Loaded }) {
  const t = useT();
  const [loaded, setLoaded] = useState<Loaded | null>(initial ?? null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [catalogue, today] = await Promise.all([readCatalogue(), readToday()]);
      setLoaded({ settings: today.settings, gyms: catalogue.gyms });
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    if (!initial) void load();
  }, [initial, load]);

  return (
    <AppSettings app={APP}>
      {notice && <Hint tone="warning">{notice}</Hint>}
      {!loaded ? (
        failed ? (
          <Hint tone="warning">{t("settings.load_failed")}</Hint>
        ) : (
          <Skeleton label={t("settings.loading")} />
        )
      ) : (
        <TrainingSettings
          settings={loaded.settings}
          gyms={loaded.gyms}
          onSettings={(settings) => setLoaded({ ...loaded, settings })}
          onGyms={(gyms) => setLoaded({ ...loaded, gyms })}
          onError={setNotice}
        />
      )}
    </AppSettings>
  );
}

interface TrainingSettingsProps {
  settings: Settings;
  gyms: Gym[];
  onSettings: (settings: Settings) => void;
  onGyms: (gyms: Gym[]) => void;
  onError: (message: string) => void;
}

function TrainingSettings({ settings, gyms, onSettings, onGyms, onError }: TrainingSettingsProps) {
  const t = useT();
  const [name, setName] = useState("");
  const [weight, setWeight] = useState<BodyWeightHistory | null>(null);
  useEffect(() => {
    readWeight()
      .then(setWeight)
      .catch(() => setWeight({ days: [], latest: null }));
  }, []);
  const fail = (error: unknown) => onError(error instanceof Error ? error.message : t("common.save_failed"));

  async function addGym() {
    if (!name.trim()) return;
    try {
      const gym = await createGym(name.trim());
      onGyms([...gyms, gym]);
      setName("");
    } catch (error) {
      fail(error);
    }
  }

  return (
    <>
      <Section title={t("settings.training")}>
        <Card>
          <div className="training-field">
            <span className="training-field-label">{t("settings.weekly_goal")}</span>
            <p className="training-field-hint">{t("settings.weekly_goal_hint")}</p>
            <Stepper
              label={t("settings.weekly_goal")}
              value={settings.weekly_goal}
              step={1}
              min={1}
              max={14}
              unit={t("settings.sessions_unit")}
              inputMode="numeric"
              onChange={(value) => {
                if (!value) return;
                onSettings({ ...settings, weekly_goal: value });
                updateSettings(value).catch(fail);
              }}
            />
          </div>
        </Card>
        <BodyWeightCard
          history={weight}
          note={t("settings.weight_note")}
          onLog={(kg) =>
            logWeight(kg)
              .then((found) => {
                setWeight(found);
                onSettings({ ...settings, bodyweight: kg });
              })
              .catch((error: unknown) => {
                fail(error);
                throw error;
              })
          }
        />
      </Section>
      <BandSection onError={fail} />
      <Section title={t("settings.gyms")}>
        <Card>
          <div className="training-field">
            <p className="training-field-hint">{t("settings.gyms_hint")}</p>
            {gyms.length > 0 && (
              <ul className="training-options">
                {gyms.map((gym) => (
                  <li key={gym.id} className="training-option" data-inactive={!gym.active || undefined}>
                    <span>{gym.name}</span>
                    <Button
                      variant="plain"
                      size="small"
                      onClick={() => {
                        const next = { ...gym, active: !gym.active };
                        onGyms(gyms.map((other) => (other.id === gym.id ? next : other)));
                        updateGym(next).catch(fail);
                      }}
                    >
                      {gym.active ? t("common.archive") : t("common.restore")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <TextField label={t("settings.new_gym")} value={name} onChange={setName} placeholder={t("settings.gym_name")} onSubmit={() => void addGym()} />
          <Button variant="secondary" size="small" icon="plus" disabled={!name.trim()} onClick={() => void addGym()}>
            {t("settings.add_gym")}
          </Button>
        </Card>
      </Section>
    </>
  );
}

export function BandSection({ onError, initial }: { onError: (error: unknown) => void; initial?: ActivityType[] }) {
  const t = useT();
  const [types, setTypes] = useState<ActivityType[] | null>(initial ?? null);
  useEffect(() => {
    if (initial) return;
    listActivityTypes()
      .then((found) => setTypes(found.filter((one) => one.active)))
      .catch(() => setTypes([]));
  }, [initial]);
  if (!types || types.length === 0) return null;
  return (
    <Section title={t("band.section")}>
      <Card>
        <p className="training-field-hint">{t("band.section_hint")}</p>
        {types.map((type) => (
          <div key={type.id} className="training-field">
            <span className="training-field-label">{type.name}</span>
            <CheckChips
              label={t("band.on_band", { name: type.name })}
              options={bandKinds(t)}
              values={type.band_kinds ?? []}
              onChange={(band_kinds) => {
                const next = { ...type, band_kinds };
                setTypes((previous) => (previous ?? []).map((one) => (one.id === type.id ? next : one)));
                updateActivityType(next).catch(onError);
              }}
            />
          </div>
        ))}
      </Card>
    </Section>
  );
}
