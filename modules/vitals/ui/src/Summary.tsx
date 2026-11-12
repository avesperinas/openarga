import {
  BodyWeightCard,
  Button,
  Collapsible,
  Columns,
  Hint,
  Inline,
  InfoHeading,
  KeyFigures,
  List,
  ListRow,
  Screen,
  Skeleton,
  Tile,
  Tiles,
  TrendTile,
  TrendTiles,
  useToast,
} from "@openarga/ui";
import { useTick } from "@openarga/app/fresh";
import { useEffect, useState } from "react";

import { AppVersion } from "./AppVersion";
import {
  type Analyte,
  type BodyOverview,
  type CheckupChanges,
  type Kpis,
  type Profile,
  type StepsSummary,
  type WeightSummary,
  Unauthorised,
  logWeight,
  readBody,
  readCheckupChanges,
  readKpis,
  readProfile,
  readSteps,
  readWeight,
  signIn,
} from "./api";
import { figureFoot, figureValue } from "./body";
import { ScreenHeader } from "./Header";
import { ageLabel, moving, movingLine, outChips, tilesOf, weeklyOf, weightMoving } from "./health";
import { INFO } from "./info";
import { EvolutionSheet } from "./Labs";
import { ProfileCard } from "./Profile";
import { changeLine } from "./summary";
import { dayLabel } from "./weight";

export type Place = "steps" | "weight" | "labs" | "sleep" | "heartday" | "rhythm";

const ABOUT: Record<string, string> = {
  heart: "El vitals en reposo, la variabilidad, el VO₂ máx. y lo demás del corazón que mide la pulsera cada día.",
  activity: "Lo que te mueves cada día: pasos, minutos activos, calorías, distancia y pisos.",
  breath: "Lo que mide la pulsera de noche: respiración, oxígeno en sangre y temperatura de la piel.",
  gait: "Cómo andas, del histórico del iPhone: velocidad, longitud del paso y simetría.",
  more: "El resto de cifras que llegan cada día y no encajan en otra categoría.",
  history: "Lo que llegaba de Apple Salud antes de la pulsera y ya no llega. Se guarda como histórico.",
  moving: "Las cifras que más se han movido en las últimas cuatro semanas contra las cinco meses de antes. Describe; no juzga.",
  labs: "Cada revisión con su PDF, la tabla de valores con su rango de referencia y la evolución de cada uno.",
};

const TITLES: Record<string, string> = { heart: "Corazón", activity: "Actividad", breath: "Noche" };

export function SummaryScreen({ go, openFigure }: { go: (place: Place) => void; openFigure: (id: string) => void }) {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [overview, setOverview] = useState<BodyOverview | null>(null);
  const [changes, setChanges] = useState<CheckupChanges | null>(null);
  const [weight, setWeight] = useState<WeightSummary | null>(null);
  const [steps, setSteps] = useState<StepsSummary | null>(null);
  const [analyte, setAnalyte] = useState<Analyte | null>(null);
  const [problem, setProblem] = useState("");
  const toast = useToast();

  const tick = useTick();

  useEffect(() => {
    const again = tick > 0;
    Promise.all([readKpis(), readProfile()])
      .then(([found, card]) => {
        setKpis(found);
        setProfile(card);
      })
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        if (!again) setProblem("No se pudo leer Vitals.");
      });
    readBody().then(setOverview).catch(() => again || setOverview(null));
    readCheckupChanges().then(setChanges).catch(() => again || setChanges(null));
    readWeight().then(setWeight).catch(() => again || setWeight(null));
    readSteps().then(setSteps).catch(() => again || setSteps(null));
  }, [tick]);

  const sections = (overview?.sections ?? []).filter((one) => one.figures.length > 0);
  const section = (id: string) => sections.find((one) => one.id === id);
  const moved = moving(overview);
  const weighed = weightMoving(kpis);
  const chips = outChips(changes);
  const checkup = changes?.checkup ?? null;
  const analytes = new Map((changes?.changes ?? []).map((one) => [one.analyte.id, one.analyte]));

  const trends = (id: string, extra?: React.ReactNode) => {
    const found = section(id);
    if (!found) return null;
    const tiles = tilesOf(found, openFigure);
    if (tiles.length === 0) return null;
    return (
      <section className="surface vitals-card" aria-label={TITLES[id] ?? found.name}>
        <InfoHeading info={ABOUT[id]}>{TITLES[id] ?? found.name}</InfoHeading>
        <TrendTiles label={TITLES[id] ?? found.name}>
          {tiles.map(({ key, ...tile }) => (
            <TrendTile key={key} {...tile} />
          ))}
        </TrendTiles>
        {extra}
      </section>
    );
  };

  const changing = (
    <section className="surface vitals-card" aria-label="Lo que está cambiando">
      <InfoHeading info={ABOUT.moving}>Lo que está cambiando</InfoHeading>
      {overview === null ? (
        <Skeleton label="Mirando lo que cambia" />
      ) : moved.length === 0 && !weighed ? (
        <Hint>Todo en tu normal este mes.</Hint>
      ) : (
        <TrendTiles label="Lo que está cambiando">
          {weighed && (
            <TrendTile
              label="Peso, media de 7 días"
              value={kpis?.weight.average_7 != null ? `${kpis.weight.average_7.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kg` : "—"}
              foot={weighed.line}
              direction={weighed.direction}
              weeks={(weight?.days ?? []).slice(-26).map((one) => one.avg7)}
              onOpen={() => go("weight")}
            />
          )}
          {moved.map((one) => (
            <TrendTile
              key={one.figure.id}
              label={one.figure.name}
              value={figureValue(one.figure, one.recent)}
              foot={movingLine(one)}
              direction={one.direction}
              weeks={one.figure.weeks ?? []}
              info={one.figure.about}
              onOpen={() => openFigure(one.figure.id)}
            />
          ))}
        </TrendTiles>
      )}
    </section>
  );

  const labs = (
    <section className="surface vitals-card" aria-label="Analíticas">
      <InfoHeading info={ABOUT.labs}>Analíticas</InfoHeading>
      {checkup ? (
        <>
          <Hint>
            {[ageLabel(checkup.day), dayLabel(checkup.day), checkup.center, `${checkup.values} valores`, checkup.document ? "PDF" : null]
              .filter(Boolean)
              .join(" · ")}
          </Hint>
          {chips.length > 0 && (
            <Inline label="Fuera de rango">
              {chips.map((chip) => (
                <Button key={chip.id} size="small" variant="tinted" onClick={() => setAnalyte(analytes.get(chip.id) ?? null)}>
                  {chip.name}
                </Button>
              ))}
            </Inline>
          )}
          {(changes?.changes ?? []).length > 0 && (
            <List>
              {(changes?.changes ?? []).slice(0, 4).map((one) => (
                <ListRow key={one.analyte.id} title={one.analyte.name} subtitle={changeLine(one)} onClick={() => setAnalyte(one.analyte)} accessory="chevron-right" />
              ))}
            </List>
          )}
        </>
      ) : (
        <Hint>Sin analíticas todavía.</Hint>
      )}
      <Button variant="tinted" onClick={() => go("labs")}>
        Todas las analíticas
      </Button>
    </section>
  );

  const body = (
    <section className="surface vitals-card" aria-label="Cuerpo">
      <InfoHeading info={INFO.weight}>Cuerpo</InfoHeading>
      <BodyWeightCard
        history={weight ? { days: weight.days.map((one) => ({ day: one.day, kg: one.kg })), latest: weight.latest ? { day: weight.latest.day, kg: weight.latest.kg } : null } : null}
        onLog={(kg) =>
          logWeight({ kg })
            .then(() => readWeight().then(setWeight))
            .catch((reason: unknown) => {
              toast({ message: reason instanceof Error ? reason.message : "No se ha podido apuntar", tone: "error" });
              throw reason;
            })
        }
      />
      <Button variant="plain" onClick={() => go("weight")}>
        Todo el peso
      </Button>
    </section>
  );

  const others = [...(section("gait")?.figures ?? []), ...(section("more")?.figures ?? [])].filter((one) => !one.historic);
  const history = section("history")?.figures ?? [];

  return (
    <Screen wide>
      <ScreenHeader title="Salud" />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {kpis === null && !problem && <Skeleton label="Cargando Salud" />}

      <Columns count={2} stack>
        <ProfileCard profile={profile} medications={false} />
        {changing}
      </Columns>
      <Columns count={2} stack>
        {body}
        {labs}
      </Columns>

      {trends(
        "heart",
        <Tiles label="Más del corazón">
          <Tile title="Vitals de cada día" hue={4} figure="curva" caption="cada 5 minutos" onOpen={() => go("heartday")} />
          <Tile title="Ritmo y electrocardiogramas" hue={4} figure="ECG" caption="avisos de ritmo" onOpen={() => go("rhythm")} />
        </Tiles>,
      )}
      {trends(
        "activity",
        steps && (
          <TrendTiles label="Pasos">
            <TrendTile
              label="Pasos, media de 7 días"
              value={steps.mean_7 != null ? Math.round(steps.mean_7).toLocaleString("es-ES") : "—"}
              foot={steps.goal ? `objetivo: ${steps.goal.toLocaleString("es-ES")}` : undefined}
              weeks={weeklyOf(steps.days.map((one) => ({ day: one.day, value: one.steps })))}
              info={INFO.steps7}
              onOpen={() => go("steps")}
            />
          </TrendTiles>
        ),
      )}
      {trends("breath")}

      {others.length > 0 && (
        <section className="surface vitals-card" aria-label="Otras cifras">
          <Collapsible title="Otras cifras" subtitle={`${others.length} cifras · marcha y más`}>
            <TrendTiles label="Otras cifras">
              {others.map((figure) => (
                <TrendTile
                  key={figure.id}
                  label={figure.name}
                  value={figure.latest ? figureValue(figure, figure.latest.value) : "—"}
                  foot={figureFoot(figure) || undefined}
                  weeks={figure.weeks ?? []}
                  info={figure.about}
                  onOpen={() => openFigure(figure.id)}
                />
              ))}
            </TrendTiles>
          </Collapsible>
        </section>
      )}
      {history.length > 0 && (
        <section className="surface vitals-card" aria-label="Lo que ya no llega">
          <Collapsible title="Lo que ya no llega" subtitle={`${history.length} cifras de Apple Salud`}>
            <Hint>{ABOUT.history}</Hint>
            <KeyFigures
              label="Lo que ya no llega"
              items={history.map((figure) => ({
                label: figure.name,
                value: figure.latest ? figureValue(figure, figure.latest.value) : "—",
                foot: figure.latest ? `último dato: ${dayLabel(figure.latest.day)}` : undefined,
                info: figure.about,
                onOpen: () => openFigure(figure.id),
              }))}
            />
          </Collapsible>
        </section>
      )}

      <Hint>Vitals enseña cifras y rangos; no diagnostica ni aconseja.</Hint>
      <AppVersion />
      {analyte && <EvolutionSheet analyte={analyte} onClose={() => setAnalyte(null)} />}
    </Screen>
  );
}
