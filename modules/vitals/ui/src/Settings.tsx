import { AppSettings, Button, CopyField, Hint, Section, SelectField, Skeleton, TextField } from "@openarga/ui";
import { useEffect, useState } from "react";

import { type Goal, Unauthorised, readGoals, readSteps, saveGoals, signIn } from "./api";
import { APP } from "./Header";
import { bandLabel, parseKg } from "./weight";

type Way = "none" | "down" | "up";

const WAYS: { value: Way; label: string }[] = [
  { value: "none", label: "Sin objetivo" },
  { value: "down", label: "Bajar" },
  { value: "up", label: "Subir" },
];

const asText = (value: number | null) => (value === null ? "" : value.toLocaleString("es-ES"));

export function parseSteps(text: string): number | null {
  const value = Number(text.trim().replace(/[.\s]/g, ""));
  return text.trim() !== "" && Number.isInteger(value) && value >= 100 && value <= 100000 ? value : null;
}

export function SettingsScreen() {
  const [goal, setGoal] = useState<Goal | null>(null);
  const [steps, setSteps] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [way, setWay] = useState<Way>("none");
  const [saying, setSaying] = useState("");

  useEffect(() => {
    readGoals()
      .then((found) => {
        setGoal(found);
        setSteps(found.steps_per_day === null ? "" : String(found.steps_per_day));
        setLow(asText(found.weight_min_kg));
        setHigh(asText(found.weight_max_kg));
        setWay(found.weight_direction ?? "none");
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying("No se pudieron leer los objetivos.");
      });
  }, []);

  const wanted: Goal = {
    steps_per_day: parseSteps(steps),
    weight_min_kg: parseKg(low),
    weight_max_kg: parseKg(high),
    weight_direction: way === "none" ? null : way,
  };
  const bad = {
    steps: steps.trim() !== "" && wanted.steps_per_day === null,
    low: low.trim() !== "" && wanted.weight_min_kg === null,
    high: high.trim() !== "" && wanted.weight_max_kg === null,
  };
  const upsideDown =
    wanted.weight_min_kg !== null && wanted.weight_max_kg !== null && wanted.weight_min_kg > wanted.weight_max_kg;
  const valid = !bad.steps && !bad.low && !bad.high && !upsideDown;

  const save = () => {
    if (!valid) return;
    saveGoals(wanted)
      .then((saved) => {
        setGoal(saved);
        setSaying("Guardado.");
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setSaying(error instanceof Error ? error.message : "No se pudo guardar.");
      });
  };

  return (
    <AppSettings app={APP}>
      {goal === null && !saying && <Skeleton label="Cargando los objetivos" />}
      {goal !== null && (
        <Section title="Objetivos">
          <div className="surface vitals-card">
            <TextField
              label="Pasos al día"
              value={steps}
              onChange={setSteps}
              inputMode="numeric"
              placeholder="8000"
              invalid={bad.steps}
              hint={bad.steps ? "Entre 100 y 100.000" : "Vacío, sin objetivo"}
            />
            <SelectField label="Peso" value={way} onChange={setWay} options={WAYS} />
            <div className="vitals-log-fields">
              <TextField
                label="Peso mínimo (kg)"
                value={low}
                onChange={setLow}
                inputMode="decimal"
                invalid={bad.low || upsideDown}
                hint={bad.low ? "Entre 20 y 400 kilos" : undefined}
              />
              <TextField
                label="Peso máximo (kg)"
                value={high}
                onChange={setHigh}
                inputMode="decimal"
                invalid={bad.high || upsideDown}
                hint={upsideDown ? "El máximo no puede ser menor que el mínimo" : bad.high ? "Entre 20 y 400 kilos" : undefined}
              />
            </div>
            <Hint>Banda de peso: {bandLabel(wanted)}</Hint>
            <Button variant="primary" block disabled={!valid} onClick={save}>
              Guardar
            </Button>
          </div>
        </Section>
      )}
      {saying && <Hint>{saying}</Hint>}
      <GoogleHealth />
      <AppleHealth />
    </AppSettings>
  );
}

export const SHORTCUT_FIELDS: { key: string; type: string; how: string }[] = [
  { key: "resting_heart_rate", type: "Frecuencia cardiaca en reposo", how: "Media" },
  { key: "heart_rate_avg", type: "Frecuencia cardiaca", how: "Media" },
  { key: "heart_rate_min", type: "Frecuencia cardiaca", how: "Mínimo" },
  { key: "heart_rate_max", type: "Frecuencia cardiaca", how: "Máximo" },
  { key: "walking_heart_rate", type: "Promedio de frecuencia cardiaca al caminar", how: "Media" },
  { key: "hrv_ms", type: "Variabilidad de la frecuencia cardiaca", how: "Media" },
  { key: "vo2max", type: "VO₂ máx.", how: "Media" },
  { key: "active_kcal", type: "Energía activa", how: "Suma" },
  { key: "basal_kcal", type: "Energía en reposo", how: "Suma" },
  { key: "distance_km", type: "Distancia a pie y corriendo (en km)", how: "Suma" },
  { key: "exercise_min", type: "Minutos de ejercicio", how: "Suma" },
  { key: "stand_min", type: "Tiempo de pie", how: "Suma" },
  { key: "flights", type: "Pisos subidos", how: "Suma" },
  { key: "walking_speed_kmh", type: "Velocidad al caminar (en km/h)", how: "Media" },
  { key: "step_length_cm", type: "Longitud del paso al caminar (en cm)", how: "Media" },
  { key: "headphone_db", type: "Exposición al audio de los auriculares", how: "Media" },
  { key: "environment_db", type: "Nivel de ruido ambiental", how: "Media" },
];

export const GOOGLE_REDIRECT = `${typeof window === "undefined" ? "" : window.location.origin}/hub/google/callback`;

function GoogleHealth() {
  const [last, setLast] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    readSteps()
      .then((found) => setLast(found.last_received))
      .catch(() => setLast(undefined));
  }, []);

  return (
    <Section title="Google Health">
      <div className="surface vitals-card">
        <Hint>
          {last
            ? `Último dato recibido: ${new Date(last).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" })}`
            : "Todavía no ha llegado nada."}
        </Hint>
        <ol className="vitals-steps">
          <li>
            En tu proyecto de <strong>Google Cloud</strong>, con la API de Google Health habilitada, el cliente OAuth de tipo
            web tiene que dejar volver a la dirección de abajo (<strong>Authorized redirect URIs</strong>). En{" "}
            <strong>Data access</strong>, los ocho permisos de lectura de Google Health: actividad, métricas de salud,
            sueño, perfil, ubicación, ECG, avisos de ritmo irregular y ajustes.
          </li>
          <li>
            En <strong>Hub</strong>, categoría Salud, conecta <strong>Google Health</strong> con el Client ID y el
            Client secret de ese cliente.
          </li>
          <li>
            Google te pide permiso: marca todas las casillas. Al volver trae los últimos treinta días, y después lo nuevo
            cada dos horas: pasos, vitals, sueño con fases, VFC, SpO₂, temperatura, entrenos, electrocardiogramas, avisos
            de ritmo irregular y la batería de la pulsera. Si conectaste antes de que se pidieran el ECG, los avisos y los
            ajustes, pulsa Reconectar en Hub.
          </li>
          <li>
            Antes de dejar el atajo del iPhone, exporta Apple Salud y cárgalo con{" "}
            <code>scripts/apple-health-steps.py</code>: así el histórico llega hasta el último día.
          </li>
        </ol>
        <CopyField label="Dirección de vuelta" value={GOOGLE_REDIRECT} />
        <Button variant="tinted" onClick={() => window.location.assign("/hub/")}>
          Abrir Hub
        </Button>
        <Hint>El Sleep Score y la Readiness no están en la API de Google: no llegan.</Hint>
      </div>
    </Section>
  );
}

export const PUSH_URL = `${typeof window === "undefined" ? "" : window.location.origin}/api/hub/push/apple-health`;

function AppleHealth() {
  const [last, setLast] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    readSteps()
      .then((found) => setLast(found.last_received))
      .catch(() => setLast(undefined));
  }, []);

  return (
    <Section title="Apple Salud, el histórico">
      <div className="surface vitals-card">
        <Hint>
          {last
            ? `Último envío: ${new Date(last).toLocaleString("es-ES", { dateStyle: "medium", timeStyle: "short" })}`
            : "Todavía no ha llegado ningún envío del iPhone."}
        </Hint>
        <details className="vitals-fields">
        <summary>Cómo se monta el atajo del iPhone</summary>
        <ol className="vitals-steps">
          <li>
            En <strong>Hub</strong>, categoría Salud, conecta <strong>Apple Salud</strong> y copia el token: solo
            se enseña esa vez.
          </li>
          <li>
            En el iPhone, abre <strong>Atajos → Automatización → Nueva</strong>, elige <strong>Hora del día</strong>, las
            23:30, cada día, y que se ejecute sin preguntar.
          </li>
          <li>
            Añade <strong>Buscar muestras de salud</strong>: tipo Pasos, fecha de inicio en los últimos 7 días, un filtro
            más <strong>Fuente contiene Watch</strong>, agrupadas por <strong>hora</strong> y sin límite. Así, si un día el
            atajo no corre, lo recoge el siguiente.
          </li>
          <li>
            Sobre ellas, <strong>Obtener detalles de muestras de salud</strong> → Fecha de inicio, y{" "}
            <strong>Formatear fecha</strong> en formato <strong>ISO 8601</strong> con la hora. Y otra vez{" "}
            <strong>Obtener detalles de muestras de salud</strong> → Valor.
          </li>
          <li>
            Repite los dos pasos anteriores con <strong>Fuente no contiene Watch</strong>: el iPhone y cualquier otra app.
          </li>
          <li>
            Añade <strong>Obtener contenido de URL</strong> con la dirección de abajo, método POST, una cabecera{" "}
            <code>Authorization</code> con <code>Bearer</code>, un espacio y el token, y cuerpo JSON con cuatro campos de
            texto: <code>watch_start</code> y <code>watch_steps</code> (las horas y los valores del Watch), y{" "}
            <code>phone_start</code> y <code>phone_steps</code> (los del resto). Cada hora cuenta la fuente que más pasos
            vio, como hace Salud: sin separarlas, el paseo que ven el iPhone y el Watch a la vez contaba dos veces.
          </li>
          <li>
            Para el resto (corazón, calorías, distancia…), antes de <strong>Obtener contenido de URL</strong>: por cada
            fila de la lista de abajo, <strong>Buscar muestras de salud</strong> de ese tipo con fecha de inicio hoy y{" "}
            <strong>Calcular estadísticas</strong> con el cálculo que dice. Cada resultado va al cuerpo JSON con su
            clave, y cuenta para el día más reciente. Las que no uses, se quedan fuera: ninguna es obligatoria.
          </li>
          <li>Si un día llega dos veces, se queda el último: a las 23:30 de hoy se corrige lo que se mandó ayer.</li>
        </ol>
        <CopyField label="Dirección del atajo" value={PUSH_URL} />
        </details>
        <details className="vitals-fields">
          <summary>Qué más puede mandar el atajo</summary>
          <dl>
            {SHORTCUT_FIELDS.map((one) => (
              <div key={one.key}>
                <dt>
                  <code>{one.key}</code>
                </dt>
                <dd>
                  {one.type} · {one.how}
                </dd>
              </div>
            ))}
          </dl>
        </details>
        <Button variant="tinted" onClick={() => window.location.assign("/hub/")}>
          Abrir Hub
        </Button>
        <Hint>
          Los nombres de las acciones pueden cambiar un poco con la versión de iOS. El histórico de antes del atajo se carga
          una vez desde el export de Apple Salud con <code>scripts/apple-health-steps.py</code>, que trae también el
          la marcha, los anillos y la ficha: grupo sanguíneo, edad y altura.
        </Hint>
      </div>
    </Section>
  );
}
