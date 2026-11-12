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
} from "@openarga/ui";
import { useCallback, useEffect, useState } from "react";

import { BAND_KINDS } from "./Activities";
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
          <Hint tone="warning">No se han podido leer los ajustes. Comprueba la conexión.</Hint>
        ) : (
          <Skeleton label="Cargando los ajustes" />
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
  const [name, setName] = useState("");
  const [weight, setWeight] = useState<BodyWeightHistory | null>(null);
  useEffect(() => {
    readWeight()
      .then(setWeight)
      .catch(() => setWeight({ days: [], latest: null }));
  }, []);
  const fail = (error: unknown) => onError(error instanceof Error ? error.message : "No se ha podido guardar");

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
      <Section title="Entreno">
        <Card>
          <div className="training-field">
            <span className="training-field-label">Objetivo semanal</span>
            <p className="training-field-hint">Sesiones por semana, de lunes a domingo. Es la medida de constancia.</p>
            <Stepper
              label="Objetivo semanal"
              value={settings.weekly_goal}
              step={1}
              min={1}
              max={14}
              unit="sesiones"
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
          note="El mismo peso en Salud y en Macros. Con él, dominadas y fondos cuentan para la fuerza."
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
      <Section title="Centros">
        <Card>
          <div className="training-field">
            <p className="training-field-hint">Cada sesión guarda dónde se hizo; por defecto, el último.</p>
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
                      {gym.active ? "Archivar" : "Recuperar"}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <TextField label="Nuevo centro" value={name} onChange={setName} placeholder="Nombre del gimnasio" onSubmit={() => void addGym()} />
          <Button variant="secondary" size="small" icon="plus" disabled={!name.trim()} onClick={() => void addGym()}>
            Añadir centro
          </Button>
        </Card>
      </Section>
    </>
  );
}

export function BandSection({ onError, initial }: { onError: (error: unknown) => void; initial?: ActivityType[] }) {
  const [types, setTypes] = useState<ActivityType[] | null>(initial ?? null);
  useEffect(() => {
    if (initial) return;
    listActivityTypes()
      .then((found) => setTypes(found.filter((one) => one.active)))
      .catch(() => setTypes([]));
  }, [initial]);
  if (!types || types.length === 0) return null;
  return (
    <Section title="Actividades y pulsera">
      <Card>
        <p className="training-field-hint">
          Lo que empieces en la pulsera entra solo como actividad, salvo los paseos. Elige cómo se llama allí cada una si
          no es el mismo nombre.
        </p>
        {types.map((type) => (
          <div key={type.id} className="training-field">
            <span className="training-field-label">{type.name}</span>
            <CheckChips
              label={`${type.name} en la pulsera`}
              options={BAND_KINDS}
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
