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
  useLocale,
  useT,
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
import { figureAbout, figureFoot, figureName, figureValue } from "./body";
import { ScreenHeader } from "./Header";
import { ageLabel, moving, movingLine, outChips, tilesOf, weeklyOf, weightMoving } from "./health";
import { EvolutionSheet } from "./Labs";
import { analyteName } from "./labs";
import { ProfileCard } from "./Profile";
import { changeLine } from "./summary";
import { dayLabel } from "./weight";
import { fixed } from "./words";

export type Place = "steps" | "weight" | "labs" | "sleep" | "heartday" | "rhythm";

const TITLED = new Set(["heart", "activity", "breath"]);

export function SummaryScreen({ go, openFigure }: { go: (place: Place) => void; openFigure: (id: string) => void }) {
  const t = useT();
  const locale = useLocale();
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
        if (!again) setProblem(t("summary.read_failed"));
      });
    readBody().then(setOverview).catch(() => again || setOverview(null));
    readCheckupChanges().then(setChanges).catch(() => again || setChanges(null));
    readWeight().then(setWeight).catch(() => again || setWeight(null));
    readSteps().then(setSteps).catch(() => again || setSteps(null));
  }, [tick, t]);

  const sections = (overview?.sections ?? []).filter((one) => one.figures.length > 0);
  const section = (id: string) => sections.find((one) => one.id === id);
  const moved = moving(overview);
  const weighed = weightMoving(kpis, t, locale);
  const chips = outChips(changes, t);
  const checkup = changes?.checkup ?? null;
  const analytes = new Map((changes?.changes ?? []).map((one) => [one.analyte.id, one.analyte]));

  const trends = (id: string, extra?: React.ReactNode) => {
    const found = section(id);
    if (!found) return null;
    const tiles = tilesOf(found, openFigure, t, locale);
    if (tiles.length === 0) return null;
    const title = TITLED.has(id) ? t(`summary.title.${id}`) : t(`group.${id}`);
    return (
      <section className="surface vitals-card" aria-label={title}>
        <InfoHeading info={t(`summary.about.${id}`)}>{title}</InfoHeading>
        <TrendTiles label={title}>
          {tiles.map(({ key, ...tile }) => (
            <TrendTile key={key} {...tile} />
          ))}
        </TrendTiles>
        {extra}
      </section>
    );
  };

  const changing = (
    <section className="surface vitals-card" aria-label={t("summary.changing")}>
      <InfoHeading info={t("summary.about.moving")}>{t("summary.changing")}</InfoHeading>
      {overview === null ? (
        <Skeleton label={t("summary.looking")} />
      ) : moved.length === 0 && !weighed ? (
        <Hint>{t("summary.all_normal")}</Hint>
      ) : (
        <TrendTiles label={t("summary.changing")}>
          {weighed && (
            <TrendTile
              label={t("summary.weight_7")}
              value={kpis?.weight.average_7 != null ? `${fixed(kpis.weight.average_7, locale, 1)} kg` : "—"}
              foot={weighed.line}
              direction={weighed.direction}
              weeks={(weight?.days ?? []).slice(-26).map((one) => one.avg7)}
              onOpen={() => go("weight")}
            />
          )}
          {moved.map((one) => (
            <TrendTile
              key={one.figure.id}
              label={figureName(t, one.figure)}
              value={figureValue(one.figure, one.recent, t, locale)}
              foot={movingLine(one, t, locale)}
              direction={one.direction}
              weeks={one.figure.weeks ?? []}
              info={figureAbout(t, one.figure)}
              onOpen={() => openFigure(one.figure.id)}
            />
          ))}
        </TrendTiles>
      )}
    </section>
  );

  const labs = (
    <section className="surface vitals-card" aria-label={t("labs.title")}>
      <InfoHeading info={t("summary.about.labs")}>{t("labs.title")}</InfoHeading>
      {checkup ? (
        <>
          <Hint>
            {[
              ageLabel(checkup.day, t),
              dayLabel(checkup.day, locale),
              checkup.center,
              t("labs.values.other", { count: checkup.values }),
              checkup.document ? "PDF" : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </Hint>
          {chips.length > 0 && (
            <Inline label={t("summary.out_of_range")}>
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
                <ListRow
                  key={one.analyte.id}
                  title={analyteName(t, one.analyte)}
                  subtitle={changeLine(one, t, locale)} onClick={() => setAnalyte(one.analyte)} accessory="chevron-right" />
              ))}
            </List>
          )}
        </>
      ) : (
        <Hint>{t("summary.no_labs")}</Hint>
      )}
      <Button variant="tinted" onClick={() => go("labs")}>
        {t("summary.all_labs")}
      </Button>
    </section>
  );

  const body = (
    <section className="surface vitals-card" aria-label={t("panel.body")}>
      <InfoHeading info={t("info.weight")}>{t("panel.body")}</InfoHeading>
      <BodyWeightCard
        history={weight ? { days: weight.days.map((one) => ({ day: one.day, kg: one.kg })), latest: weight.latest ? { day: weight.latest.day, kg: weight.latest.kg } : null } : null}
        onLog={(kg) =>
          logWeight({ kg })
            .then(() => readWeight().then(setWeight))
            .catch((reason: unknown) => {
              toast({ message: reason instanceof Error ? reason.message : t("weight.log_failed"), tone: "error" });
              throw reason;
            })
        }
      />
      <Button variant="plain" onClick={() => go("weight")}>
        {t("summary.all_weight")}
      </Button>
    </section>
  );

  const others = [...(section("gait")?.figures ?? []), ...(section("more")?.figures ?? [])].filter((one) => !one.historic);
  const history = section("history")?.figures ?? [];

  return (
    <Screen wide>
      <ScreenHeader title={t("tabs.health")} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      {kpis === null && !problem && <Skeleton label={t("summary.loading")} />}

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
        <Tiles label={t("summary.more_heart")}>
          <Tile
            title={t("figure.heart_each_day")}
            hue={4}
            figure={t("summary.curve")}
            caption={t("summary.every_5")}
            onOpen={() => go("heartday")}
          />
          <Tile
            title={t("summary.rhythm_ecg")}
            hue={4}
            figure="ECG"
            caption={t("summary.rhythm_alerts")}
            onOpen={() => go("rhythm")}
          />
        </Tiles>,
      )}
      {trends(
        "activity",
        steps && (
          <TrendTiles label={t("steps.title")}>
            <TrendTile
              label={t("summary.steps_7")}
              value={steps.mean_7 != null ? Math.round(steps.mean_7).toLocaleString(locale) : "—"}
              foot={steps.goal ? t("summary.goal", { goal: steps.goal.toLocaleString(locale) }) : undefined}
              weeks={weeklyOf(steps.days.map((one) => ({ day: one.day, value: one.steps })))}
              info={t("info.steps7")}
              onOpen={() => go("steps")}
            />
          </TrendTiles>
        ),
      )}
      {trends("breath")}

      {others.length > 0 && (
        <section className="surface vitals-card" aria-label={t("summary.others")}>
          <Collapsible title={t("summary.others")} subtitle={t("summary.others_sub", { count: others.length })}>
            <TrendTiles label={t("summary.others")}>
              {others.map((figure) => (
                <TrendTile
                  key={figure.id}
                  label={figureName(t, figure)}
                  value={figure.latest ? figureValue(figure, figure.latest.value, t, locale) : "—"}
                  foot={figureFoot(figure, t, locale) || undefined}
                  weeks={figure.weeks ?? []}
                  info={figureAbout(t, figure)}
                  onOpen={() => openFigure(figure.id)}
                />
              ))}
            </TrendTiles>
          </Collapsible>
        </section>
      )}
      {history.length > 0 && (
        <section className="surface vitals-card" aria-label={t("summary.gone")}>
          <Collapsible title={t("summary.gone")} subtitle={t("summary.gone_sub", { count: history.length })}>
            <Hint>{t("summary.about.history")}</Hint>
            <KeyFigures
              label={t("summary.gone")}
              items={history.map((figure) => ({
                label: figureName(t, figure),
                value: figure.latest ? figureValue(figure, figure.latest.value, t, locale) : "—",
                foot: figure.latest ? t("summary.last_data", { day: dayLabel(figure.latest.day, locale) }) : undefined,
                info: figureAbout(t, figure),
                onOpen: () => openFigure(figure.id),
              }))}
            />
          </Collapsible>
        </section>
      )}

      <Hint>{t("summary.disclaimer")}</Hint>
      <AppVersion />
      {analyte && <EvolutionSheet analyte={analyte} onClose={() => setAnalyte(null)} />}
    </Screen>
  );
}
